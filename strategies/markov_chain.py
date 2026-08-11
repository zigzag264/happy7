# -*- coding: utf-8 -*-
"""
① 马尔科夫链预测模型
基于状态转移概率矩阵预测下一期号码
"""

import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, get_interval,
    compute_frequency, validate_prediction_group
)


class MarkovChainStrategy(BaseStrategy):
    """马尔科夫链预测模型"""

    MODEL_ID = "markov-chain"
    MODEL_NAME = "马尔科夫链"
    MODEL_TYPE = "statistical"

    def _build_transition_matrix(self, data: List[Dict], pool_size: int = 35,
                                  key: str = "front_balls") -> Dict[str, Dict[str, int]]:
        """构建一阶转移概率矩阵"""
        matrix = defaultdict(lambda: defaultdict(int))
        for i in range(1, len(data)):
            prev_balls = data[i - 1].get(key, [])
            curr_balls = data[i].get(key, [])
            for pb in prev_balls:
                for cb in curr_balls:
                    matrix[pb][cb] += 1
        return matrix

    def _build_second_order_matrix(self, data: List[Dict], pool_size: int = 35,
                                    key: str = "front_balls") -> Dict[Tuple[str, str], Dict[str, int]]:
        """构建二阶转移概率矩阵"""
        matrix = defaultdict(lambda: defaultdict(int))
        for i in range(2, len(data)):
            prev_balls = data[i - 2].get(key, [])
            curr_balls = data[i - 1].get(key, [])
            next_balls = data[i].get(key, [])
            for pb in prev_balls:
                for cb in curr_balls:
                    key_pair = (pb, cb)
                    for nb in next_balls:
                        matrix[key_pair][nb] += 1
        return matrix

    def _build_interval_transition(self, data: List[Dict]) -> Tuple[Dict, Dict]:
        """构建区间转移矩阵"""
        interval_matrix = defaultdict(lambda: defaultdict(int))
        value_matrix = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

        for i in range(1, len(data)):
            prev_intervals = [get_interval(b) for b in data[i-1].get("front_balls", [])]
            curr_intervals = [get_interval(b) for b in data[i].get("front_balls", [])]

            for pi in prev_intervals:
                for ci in curr_intervals:
                    interval_matrix[pi][ci] += 1

            for pb in data[i-1].get("front_balls", []):
                pi = get_interval(pb)
                for cb in data[i].get("front_balls", []):
                    ci = get_interval(cb)
                    value_matrix[pi][ci][cb] += 1

        return interval_matrix, value_matrix

    def _predict_by_transition(self, matrix: Dict, last_balls: List[str],
                                pool_size: int) -> Tuple[List[str], str]:
        """基于转移矩阵预测"""
        scores = defaultdict(float)
        for pb in last_balls:
            if pb in matrix:
                total = sum(matrix[pb].values())
                if total > 0:
                    for cb, count in matrix[pb].items():
                        scores[cb] += count / total

        for i in range(1, pool_size + 1):
            b = format_ball(i)
            if b not in scores:
                scores[b] = 0.0

        sorted_balls = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top5 = [b for b, _ in sorted_balls[:5]]

        # 确保5个
        all_balls = [format_ball(i) for i in range(1, pool_size + 1)]
        remaining = [b for b in all_balls if b not in top5]
        while len(top5) < 5:
            top5.append(remaining.pop(0))

        detail = f"一阶转移: P(Top)={sorted_balls[0][1]:.3f}"
        return sort_balls(top5), detail

    def _predict_second_order(self, matrix: Dict, last_two: List[Tuple[str, str]],
                               pool_size: int) -> Tuple[List[str], str]:
        """基于二阶转移矩阵预测"""
        scores = defaultdict(float)
        for pair in last_two:
            if pair in matrix:
                total = sum(matrix[pair].values())
                if total > 0:
                    for nb, count in matrix[pair].items():
                        scores[nb] += count / total

        for i in range(1, pool_size + 1):
            b = format_ball(i)
            if b not in scores:
                scores[b] = 0.0

        sorted_balls = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top5 = [b for b, _ in sorted_balls[:5]]

        all_balls = [format_ball(i) for i in range(1, pool_size + 1)]
        remaining = [b for b in all_balls if b not in top5]
        while len(top5) < 5:
            top5.append(remaining.pop(0))

        return sort_balls(top5), f"二阶转移: P(Top)={sorted_balls[0][1]:.3f}"

    def _predict_by_interval(self, interval_matrix: Dict, value_matrix: Dict,
                              last_balls: List[str], pool_size: int = 35) -> Tuple[List[str], str]:
        """基于区间转移预测"""
        last_intervals = [get_interval(b) for b in last_balls]
        interval_counts = Counter(last_intervals)

        # 预测下一期区间分布
        pred_intervals = []
        for _ in range(5):
            scores = {}
            for li in interval_counts:
                if li in interval_matrix:
                    total = sum(interval_matrix[li].values())
                    if total > 0:
                        for ci, count in interval_matrix[li].items():
                            scores[ci] = scores.get(ci, 0) + count / total * interval_counts[li]
            if not scores:
                pred_intervals.append(random.randint(0, 2))
            else:
                pred_intervals.append(max(scores, key=scores.get))

        # 在每个区间内选号码
        result = []
        for pi in pred_intervals:
            candidates = []
            for li in interval_counts:
                if li in value_matrix and pi in value_matrix[li]:
                    candidates.extend(value_matrix[li][pi].keys())
            if candidates:
                freq = Counter(candidates)
                # 选未选过的
                available = [b for b, _ in freq.most_common() if b not in result]
                if available:
                    result.append(available[0])
                else:
                    result.append(freq.most_common(1)[0][0])
            else:
                # 区间内随机
                for b in last_balls:
                    if get_interval(b) == pi:
                        candidates.append(b)
                result.append(candidates[0] if candidates else format_ball(pi * 12 + 1))

        return sort_balls(result), f"区间转移: 分布{get_interval_distribution(result)}"

    def _predict_back_balls(self, data: List[Dict]) -> Tuple[List[str], str]:
        """预测后区号码"""
        matrix = self._build_transition_matrix(data, 12, "back_balls")
        if not data:
            return ["01", "02"], "后区默认"

        last_balls = data[0].get("back_balls", ["01", "02"])
        scores = defaultdict(float)
        for pb in last_balls:
            if pb in matrix:
                total = sum(matrix[pb].values())
                if total > 0:
                    for cb, count in matrix[pb].items():
                        scores[cb] += count / total

        for i in range(1, 13):
            b = format_ball(i)
            if b not in scores:
                scores[b] = 0.0

        sorted_balls = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top2 = [b for b, _ in sorted_balls[:2]]

        all_balls = [format_ball(i) for i in range(1, 13)]
        remaining = [b for b in all_balls if b not in top2]
        while len(top2) < 2:
            top2.append(remaining.pop(0))

        return sort_balls(top2), f"后区转移: P(Top)={sorted_balls[0][1]:.3f}"

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        last_draw = data[0]
        last_fronts = last_draw.get("front_balls", [])
        last_backs = last_draw.get("back_balls", [])

        # 构建转移矩阵
        front_matrix = self._build_transition_matrix(data, 35, "front_balls")
        second_order_matrix = self._build_second_order_matrix(data, 35, "front_balls")
        interval_matrix, value_matrix = self._build_interval_transition(data)

        # 构建二阶转移的 last_two pairs
        if len(data) >= 2:
            second_last = data[1].get("front_balls", [])
            last_two_pairs = [(pb, cb) for pb in second_last for cb in last_fronts]
        else:
            last_two_pairs = []

        # 1. 一阶转移预测
        front1, desc1 = self._predict_by_transition(front_matrix, last_fronts, 35)
        back1, back_desc1 = self._predict_back_balls(data)

        # 2. 二阶转移预测
        if last_two_pairs:
            front2, desc2 = self._predict_second_order(second_order_matrix, last_two_pairs, 35)
        else:
            front2, desc2 = front1, desc1
        back2, _ = self._predict_back_balls(data)

        # 3. 区间压缩预测
        front3, desc3 = self._predict_by_interval(interval_matrix, value_matrix, last_fronts, 35)
        back3, _ = self._predict_back_balls(data)

        # 4. 加权混合（一阶+二阶加权）
        scores_combined = defaultdict(float)
        # 一阶分数
        for pb in last_fronts:
            if pb in front_matrix:
                total = sum(front_matrix[pb].values())
                if total > 0:
                    for cb, count in front_matrix[pb].items():
                        scores_combined[cb] += count / total * 0.6
        # 二阶分数
        if last_two_pairs:
            for pair in last_two_pairs:
                if pair in second_order_matrix:
                    total = sum(second_order_matrix[pair].values())
                    if total > 0:
                        for nb, count in second_order_matrix[pair].items():
                            scores_combined[nb] += count / total * 0.4

        for i in range(1, 36):
            b = format_ball(i)
            if b not in scores_combined:
                scores_combined[b] = 0.0

        sorted_combined = sorted(scores_combined.items(), key=lambda x: x[1], reverse=True)
        front4 = [b for b, _ in sorted_combined[:5]]
        all_balls = [format_ball(i) for i in range(1, 36)]
        remaining = [b for b in all_balls if b not in front4]
        while len(front4) < 5:
            front4.append(remaining.pop(0))
        front4 = sort_balls(front4)
        back4, _ = self._predict_back_balls(data)

        # 构建描述
        from .base import get_interval_distribution, compute_sum
        d1 = f"{desc1}；区间{get_interval_distribution(front1)}；{back_desc1}；和值{compute_sum(front1)}"
        d2 = f"{desc2}；区间{get_interval_distribution(front2)}；和值{compute_sum(front2)}"
        d3 = f"{desc3}；{back_desc1}；和值{compute_sum(front3)}"
        d4 = f"加权混合(一阶×0.6+二阶×0.4)；P(Top)={sorted_combined[0][1]:.3f}；和值{compute_sum(front4)}"

        # 各策略的描述
        strategies = [
            ("一阶马尔科夫链", front1, back1, d1),
            ("二阶马尔科夫链", front2, back2, d2),
            ("区间压缩马尔科夫", front3, back3, d3),
            ("加权混合马尔科夫", front4, back4, d4),
        ]

        predictions = []
        for gid, (name, fronts, backs, desc) in enumerate(strategies, 1):
            pred = {
                "group_id": gid,
                "strategy": name,
                "front_balls": fronts,
                "back_balls": backs,
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)


def get_interval_distribution(fronts):
    """计算区间分布"""
    from .base import get_interval
    return f"{sum(1 for b in fronts if get_interval(b) == 0)}-{sum(1 for b in fronts if get_interval(b) == 1)}-{sum(1 for b in fronts if get_interval(b) == 2)}"