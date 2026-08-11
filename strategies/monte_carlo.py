# -*- coding: utf-8 -*-
"""
④ 蒙特卡洛模拟预测模型
通过大量约束随机采样，统计号码出现频率
"""

import random
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    get_interval, compute_sum, validate_prediction_group
)


class MonteCarloStrategy(BaseStrategy):
    """蒙特卡洛模拟预测模型"""

    MODEL_ID = "monte-carlo"
    MODEL_NAME = "蒙特卡洛模拟"
    MODEL_TYPE = "statistical"

    def _sample_front(self, weights: Dict[str, float], used: set) -> str:
        """按权重采样一个前区号码"""
        candidates = [b for b in weights if b not in used]
        if not candidates:
            candidates = [format_ball(i) for i in range(1, 36) if format_ball(i) not in used]
        weights_list = [weights.get(c, 0.01) for c in candidates]
        total = sum(weights_list)
        if total <= 0:
            return random.choice(candidates)
        probs = [w / total for w in weights_list]
        return random.choices(candidates, weights=probs, k=1)[0]

    def _sample_back(self, weights: Dict[str, float], used: set) -> str:
        """按权重采样一个后区号码"""
        candidates = [b for b in weights if b not in used]
        if not candidates:
            candidates = [format_ball(i) for i in range(1, 13) if format_ball(i) not in used]
        weights_list = [weights.get(c, 0.01) for c in candidates]
        total = sum(weights_list)
        if total <= 0:
            return random.choice(candidates)
        probs = [w / total for w in weights_list]
        return random.choices(candidates, weights=probs, k=1)[0]

    def _check_constraints(self, fronts: List[str], min_sum: int = 80,
                            max_sum: int = 120, require_parity: bool = True) -> bool:
        """检查是否满足约束条件"""
        # 和值约束
        s = compute_sum(fronts)
        if s < min_sum or s > max_sum:
            return False

        # 奇偶比约束
        if require_parity:
            odd = sum(1 for b in fronts if int(b) % 2 == 1)
            if odd not in [2, 3]:
                return False

        return True

    def _run_simulation(self, front_weights: Dict[str, float],
                         back_weights: Dict[str, float],
                         n_samples: int, min_sum: int, max_sum: int,
                         require_parity: bool = True) -> Tuple[List[str], List[str]]:
        """运行蒙特卡洛模拟"""
        front_counter = Counter()
        back_counter = Counter()
        valid_samples = 0

        for _ in range(max(n_samples * 2, 10000)):  # 多采样以保证有效样本
            if valid_samples >= n_samples:
                break

            # 前区采样
            fronts = []
            used = set()
            for _ in range(5):
                b = self._sample_front(front_weights, used)
                fronts.append(b)
                used.add(b)

            if not self._check_constraints(fronts, min_sum, max_sum, require_parity):
                continue

            # 后区采样
            backs = []
            used_back = set()
            for _ in range(2):
                b = self._sample_back(back_weights, used_back)
                backs.append(b)
                used_back.add(b)

            for b in fronts:
                front_counter[b] += 1
            for b in backs:
                back_counter[b] += 1
            valid_samples += 1

        # 按频率排序
        top_fronts = [b for b, _ in front_counter.most_common(5)]
        top_backs = [b for b, _ in back_counter.most_common(2)]

        # 确保有足够的号码
        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]
        for b in all_fronts:
            if b not in top_fronts:
                top_fronts.append(b)
        for b in all_backs:
            if b not in top_backs:
                top_backs.append(b)

        return top_fronts[:5], top_backs[:2]

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        # 计算频率作为权重
        front_freq = compute_frequency(data, 35, "front_balls")
        back_freq = compute_frequency(data, 12, "back_balls")

        # 为未出现的号码设置最小概率
        max_front_freq = max(front_freq.values()) if front_freq else 1
        max_back_freq = max(back_freq.values()) if back_freq else 1

        front_weights = {}
        for i in range(1, 36):
            b = format_ball(i)
            front_weights[b] = max(front_freq.get(b, 0), 0.1)

        back_weights = {}
        for i in range(1, 13):
            b = format_ball(i)
            back_weights[b] = max(back_freq.get(b, 0), 0.1)

        # 4 组策略
        # 1. 大量采样 + 宽松约束
        random.seed(42)
        front1, back1 = self._run_simulation(front_weights, back_weights,
                                              n_samples=2000, min_sum=80, max_sum=120)
        d1 = f"2k次采样；和值{compute_sum(front1)}；约束满足率高"

        # 2. 中等采样 + 严格约束
        front2, back2 = self._run_simulation(front_weights, back_weights,
                                              n_samples=3000, min_sum=85, max_sum=115)
        d2 = f"3k次采样；和值{compute_sum(front2)}；严格约束"

        # 3. 重要性采样（指数衰减权重）
        recent_weights = {}
        for i in range(1, 36):
            b = format_ball(i)
            # 给近期出现的号码更高权重
            w = front_weights[b]
            for idx, draw in enumerate(data[:10]):
                if b in draw.get("front_balls", []):
                    w *= 1.5 ** (10 - idx)  # 越近权重越高
            recent_weights[b] = w

        front3, back3 = self._run_simulation(recent_weights, back_weights,
                                              n_samples=5000, min_sum=80, max_sum=120)
        d3 = f"5k次重要性采样(近期加权)；和值{compute_sum(front3)}"

        # 4. 均值回归（偏向冷号）
        cold_weights = {}
        for i in range(1, 36):
            b = format_ball(i)
            # 对近期未出现的号码给予更高权重
            missing = 0
            for draw in data[:10]:
                if b not in draw.get("front_balls", []):
                    missing += 1
            cold_weights[b] = front_weights[b] * (1 + missing * 0.2)

        front4, back4 = self._run_simulation(cold_weights, back_weights,
                                              n_samples=3000, min_sum=75, max_sum=125,
                                              require_parity=False)
        d4 = f"3k次均值回归(冷号加权)；和值{compute_sum(front4)}"

        from .base import get_interval_distribution

        strategies = [
            ("万次均衡采样", front1, back1, d1),
            ("五万次严格约束", front2, back2, d2),
            ("十万次重要性采样", front3, back3, d3),
            ("均值回归采样", front4, back4, d4),
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