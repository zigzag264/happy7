# -*- coding: utf-8 -*-
"""
⑩ 组合约束满足 CSP 预测模型
通过约束求解搜索满足所有约束的号码组合
"""

import random
from itertools import combinations
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    get_interval, compute_sum, validate_prediction_group
)


class CSPStrategy(BaseStrategy):
    """组合约束满足 CSP 预测模型"""

    MODEL_ID = "constraint-satisfaction"
    MODEL_NAME = "组合约束CSP"
    MODEL_TYPE = "statistical"

    def _ac_value(self, fronts: List[str]) -> int:
        """计算 AC 值（号码离散度）"""
        diffs = set()
        for a, b in combinations(fronts, 2):
            diffs.add(abs(int(a) - int(b)))
        return len(diffs) - (len(fronts) - 1)

    def _has_consecutive(self, fronts: List[str]) -> int:
        """计算连号对数"""
        nums = sorted(int(b) for b in fronts)
        count = 0
        for i in range(1, len(nums)):
            if nums[i] - nums[i-1] == 1:
                count += 1
        return count

    def _check_hard_constraints(self, fronts: List[str],
                                 min_sum: int, max_sum: int,
                                 ac_min: int, ac_max: int,
                                 max_consecutive: int) -> bool:
        """检查硬约束"""
        # 和值
        s = compute_sum(fronts)
        if s < min_sum or s > max_sum:
            return False

        # 奇偶比
        odd = sum(1 for b in fronts if int(b) % 2 == 1)
        if odd not in [2, 3]:
            return False

        # AC 值
        ac = self._ac_value(fronts)
        if ac < ac_min or ac > ac_max:
            return False

        # 连号
        if self._has_consecutive(fronts) > max_consecutive:
            return False

        # 区间覆盖：至少 2 个区间
        intervals = set(get_interval(b) for b in fronts)
        if len(intervals) < 2:
            return False

        return True

    def _soft_score(self, fronts: List[str], backs: List[str],
                     want_sum: int) -> float:
        """计算软约束得分"""
        score = 0.0
        s = compute_sum(fronts)
        score += 100.0 - abs(s - want_sum)  # 越靠近目标和值分越高
        return score

    def _generate_candidates(self, all_fronts: List[str], count: int) -> List[List[str]]:
        """生成满足硬约束的候选组合"""
        results = []
        attempts = 0
        while len(results) < count and attempts < 5000:
            attempts += 1
            fronts = random.sample(all_fronts, 5)
            if self._check_hard_constraints(fronts, 80, 120, 4, 12, 2):
                results.append(sort_balls(fronts))
        return results

    def _select_backs(self) -> List[str]:
        """选择后区号码"""
        freq = compute_frequency(self.history_data, 12, "back_balls")
        sorted_items = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        backs = [b for b, _ in sorted_items[:2]]
        all_backs = [format_ball(i) for i in range(1, 13)]
        for b in all_backs:
            if len(backs) >= 2:
                break
            if b not in backs:
                backs.append(b)
        return sort_balls(backs[:2])

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        all_fronts = [format_ball(i) for i in range(1, 36)]

        # 4 组策略：不同目标约束
        strategies_config = [
            dict(label="和值最优", min_sum=85, max_sum=115, want_sum=100),
            dict(label="奇偶平衡", min_sum=80, max_sum=120, want_sum=90),
            dict(label="区间均衡", min_sum=75, max_sum=125, want_sum=95),
            dict(label="综合软约束", min_sum=70, max_sum=130, want_sum=100),
        ]

        back_candidates = self._select_backs()

        predictions = []
        for config in strategies_config:
            random.seed(42)
            candidates = self._generate_candidates(all_fronts, 20)

            best_fronts = None
            best_score = float('-inf')
            for fronts in candidates:
                score = self._soft_score(fronts, back_candidates, config["want_sum"])
                if score > best_score:
                    best_score = score
                    best_fronts = fronts

            if best_fronts is None:
                best_fronts = sort_balls(random.sample(all_fronts, 5))

            desc = (f"{config['label']}(软约束目标和值={config['want_sum']})；"
                    f"硬约束: 和值({config['min_sum']}-{config['max_sum']}), AC值, 奇偶2:3/3:2；"
                    f"求解到得分{best_score:.0f}")

            pred = {
                "group_id": len(predictions) + 1,
                "strategy": f"CSP-{config['label']}",
                "front_balls": sort_balls(best_fronts),
                "back_balls": back_candidates,
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)