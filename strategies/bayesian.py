# -*- coding: utf-8 -*-
"""
② 贝叶斯推断预测模型
使用 Beta-Binomial 共轭先验更新，在线学习号码概率
"""

import math
from collections import defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    compute_missing, validate_prediction_group
)


class BayesianStrategy(BaseStrategy):
    """贝叶斯推断预测模型"""

    MODEL_ID = "bayesian-inference"
    MODEL_NAME = "贝叶斯推断"
    MODEL_TYPE = "statistical"

    def _beta_posterior(self, alpha0: float, beta0: float, k: int, n: int) -> float:
        """计算 Beta 后验期望"""
        return (alpha0 + k) / (alpha0 + beta0 + n)

    def _compute_posterior_probs(self, data: List[Dict], pool_size: int,
                                  key: str, prior_alpha: float,
                                  prior_beta: float, window: int = 0) -> Dict[str, float]:
        """计算后验概率"""
        if window > 0:
            data = data[:window]

        freq = compute_frequency(data, pool_size, key)
        n = len(data)

        probs = {}
        for i in range(1, pool_size + 1):
            b = format_ball(i)
            k = freq.get(b, 0)
            posterior = self._beta_posterior(prior_alpha, prior_beta, k, n)
            probs[b] = posterior

        return probs

    def _select_top(self, probs: Dict[str, float], count: int) -> List[str]:
        """选择概率最高的 count 个号码"""
        sorted_items = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        return [item[0] for item in sorted_items[:count]]

    def _ensure_count(self, selected: List[str], probs: Dict[str, float],
                       all_pool: List[str], count: int) -> List[str]:
        """确保有 count 个号码"""
        result = list(selected)
        remaining = sorted([b for b in all_pool if b not in result],
                          key=lambda b: probs.get(b, 0), reverse=True)
        while len(result) < count:
            result.append(remaining.pop(0))
        return result

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        # 1. 弱先验：Beta(1, 1) 均匀分布
        probs_f1 = self._compute_posterior_probs(data, 35, "front_balls", 1, 1)
        probs_b1 = self._compute_posterior_probs(data, 12, "back_balls", 1, 1)
        front1 = self._select_top(probs_f1, 5)
        front1 = self._ensure_count(front1, probs_f1, all_fronts, 5)
        back1 = self._select_top(probs_b1, 2)
        back1 = self._ensure_count(back1, probs_b1, all_backs, 2)

        # 2. 中先验：Beta(3, 27) 假设历史平均频率
        probs_f2 = self._compute_posterior_probs(data, 35, "front_balls", 3, 27)
        probs_b2 = self._compute_posterior_probs(data, 12, "back_balls", 3, 27)
        front2 = self._select_top(probs_f2, 5)
        front2 = self._ensure_count(front2, probs_f2, all_fronts, 5)
        back2 = self._select_top(probs_b2, 2)
        back2 = self._ensure_count(back2, probs_b2, all_backs, 2)

        # 3. 强先验：Beta(10, 90)
        probs_f3 = self._compute_posterior_probs(data, 35, "front_balls", 10, 90)
        probs_b3 = self._compute_posterior_probs(data, 12, "back_balls", 10, 90)
        front3 = self._select_top(probs_f3, 5)
        front3 = self._ensure_count(front3, probs_f3, all_fronts, 5)
        back3 = self._select_top(probs_b3, 2)
        back3 = self._ensure_count(back3, probs_b3, all_backs, 2)

        # 4. 自适应滑动窗口（最近15期）
        window = min(15, len(data))
        probs_f4 = self._compute_posterior_probs(data, 35, "front_balls", 2, 13, window)
        probs_b4 = self._compute_posterior_probs(data, 12, "back_balls", 2, 13, window)
        front4 = self._select_top(probs_f4, 5)
        front4 = self._ensure_count(front4, probs_f4, all_fronts, 5)
        back4 = self._select_top(probs_b4, 2)
        back4 = self._ensure_count(back4, probs_b4, all_backs, 2)

        from .base import get_interval_distribution, compute_sum

        d1 = f"弱先验Beta(1,1)；P(Top)={probs_f1[front1[0]]:.3f}；区间{get_interval_distribution(front1)}；和值{compute_sum(front1)}"
        d2 = f"中先验Beta(3,27)；P(Top)={probs_f2[front2[0]]:.3f}；区间{get_interval_distribution(front2)}；和值{compute_sum(front2)}"
        d3 = f"强先验Beta(10,90)；P(Top)={probs_f3[front3[0]]:.3f}；区间{get_interval_distribution(front3)}；和值{compute_sum(front3)}"
        d4 = f"滑动窗口{window}期+Beta(2,13)；P(Top)={probs_f4[front4[0]]:.3f}；和值{compute_sum(front4)}"

        strategies = [
            ("弱先验贝叶斯", front1, back1, d1),
            ("中先验贝叶斯", front2, back2, d2),
            ("强先验贝叶斯", front3, back3, d3),
            ("自适应滑动窗口", front4, back4, d4),
        ]

        predictions = []
        for gid, (name, fronts, backs, desc) in enumerate(strategies, 1):
            pred = {
                "group_id": gid,
                "strategy": name,
                "front_balls": sort_balls(fronts),
                "back_balls": sort_balls(backs),
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)