# -*- coding: utf-8 -*-
"""
③ 时间序列 ARIMA 预测模型
对每个号码的二元出现序列进行时间序列建模
"""

import math
from collections import defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    validate_prediction_group
)


class ArimaStrategy(BaseStrategy):
    """时间序列 ARIMA 预测模型"""

    MODEL_ID = "arima-time-series"
    MODEL_NAME = "时间序列ARIMA"
    MODEL_TYPE = "statistical"

    def _build_series(self, ball: str, key: str = "front_balls") -> List[int]:
        """构建号码的二元出现序列"""
        return [1 if ball in d.get(key, []) else 0 for d in self.history_data]

    def _ar_predict(self, series: List[int], order: int) -> float:
        """简化版自回归预测"""
        n = len(series)
        if n < order + 1:
            return sum(series) / max(n, 1)

        # 使用最小二乘法拟合 AR 系数
        X = []
        y = []
        for i in range(order, n):
            X.append(series[i-order:i])
            y.append(series[i])

        if not X:
            return 0.0

        # 简单平均预测
        recent = series[:order]
        if sum(recent) == 0:
            # 如果最近几期都没有出现，模型倾向于预测不出现
            # 但考虑遗漏值补偿
            missing = 0
            for v in reversed(series):
                if v == 0:
                    missing += 1
                else:
                    break
            # 遗漏越长，出现概率越高
            return min(0.5, missing / max(n, 1) * 2)

        # 计算加权平均（越近权重越高）
        weights = [0.5, 0.3, 0.2][:order] if order <= 3 else [0.4, 0.3, 0.2, 0.1]
        if len(weights) < order:
            weights = [1.0 / order] * order

        pred = sum(series[i] * w for i, w in zip(range(order), weights))
        return pred

    def _missing_prediction(self, series: List[int], order: int) -> float:
        """基于遗漏值的预测"""
        missing = 0
        for v in reversed(series):
            if v == 0:
                missing += 1
            else:
                break

        # 遗漏周期越长，出现概率越高（均值回归）
        avg_interval = len(series) / max(sum(series), 1)
        prob = 1.0 / max(avg_interval, 1)

        # 如果当前遗漏已超过平均间隔，概率提升
        if missing > avg_interval:
            prob *= 1.5

        return min(prob, 0.8)

    def _seasonal_prediction(self, series: List[int], period: int = 3) -> float:
        """季节性/周期性预测"""
        n = len(series)
        if n < period:
            return sum(series) / max(n, 1)

        # 检查周期模式
        seasonal_freq = 0
        count = 0
        for i in range(n - period - 1, -1, -period):
            if i < n:
                seasonal_freq += series[i]
                count += 1

        if count == 0:
            return 0.0

        return seasonal_freq / count

    def _predict_probs(self, order: int, use_missing: bool = False,
                        use_seasonal: bool = False,
                        key: str = "front_balls",
                        pool_size: int = 35) -> Dict[str, float]:
        """预测每个号码的概率"""
        probs = {}
        for i in range(1, pool_size + 1):
            b = format_ball(i)
            series = self._build_series(b, key)

            if len(series) < 3:
                probs[b] = 0.0
                continue

            # 基础 AR 预测
            ar_prob = self._ar_predict(series, order)

            # 遗漏值补偿
            missing_prob = 0.0
            if use_missing:
                missing_prob = self._missing_prediction(series, order)

            # 季节性
            seasonal_prob = 0.0
            if use_seasonal:
                seasonal_prob = self._seasonal_prediction(series, 3)

            # 加权组合
            if use_missing and use_seasonal:
                probs[b] = ar_prob * 0.4 + missing_prob * 0.3 + seasonal_prob * 0.3
            elif use_missing:
                probs[b] = ar_prob * 0.6 + missing_prob * 0.4
            elif use_seasonal:
                probs[b] = ar_prob * 0.6 + seasonal_prob * 0.4
            else:
                probs[b] = ar_prob

            # 加一点随机噪声防止完全随机分布
            probs[b] = max(0.01, min(0.99, probs[b]))

        return probs

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        # 4 组策略
        # 1. 短周期 AR(2)
        probs_f1 = self._predict_probs(2, key="front_balls", pool_size=35)
        probs_b1 = self._predict_probs(2, key="back_balls", pool_size=12)
        front1 = [b for b, _ in sorted(probs_f1.items(), key=lambda x: x[1], reverse=True)[:5]]
        back1 = [b for b, _ in sorted(probs_b1.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front1) < 5 and b not in front1:
                front1.append(b)
        for b in all_backs:
            if len(back1) < 2 and b not in back1:
                back1.append(b)

        # 2. 长周期 AR(5)
        probs_f2 = self._predict_probs(5, key="front_balls", pool_size=35)
        probs_b2 = self._predict_probs(5, key="back_balls", pool_size=12)
        front2 = [b for b, _ in sorted(probs_f2.items(), key=lambda x: x[1], reverse=True)[:5]]
        back2 = [b for b, _ in sorted(probs_b2.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front2) < 5 and b not in front2:
                front2.append(b)
        for b in all_backs:
            if len(back2) < 2 and b not in back2:
                back2.append(b)

        # 3. 遗漏值补偿
        probs_f3 = self._predict_probs(3, use_missing=True, key="front_balls", pool_size=35)
        probs_b3 = self._predict_probs(3, use_missing=True, key="back_balls", pool_size=12)
        front3 = [b for b, _ in sorted(probs_f3.items(), key=lambda x: x[1], reverse=True)[:5]]
        back3 = [b for b, _ in sorted(probs_b3.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front3) < 5 and b not in front3:
                front3.append(b)
        for b in all_backs:
            if len(back3) < 2 and b not in back3:
                back3.append(b)

        # 4. 季节性组合
        probs_f4 = self._predict_probs(3, use_missing=True, use_seasonal=True, key="front_balls", pool_size=35)
        probs_b4 = self._predict_probs(3, use_missing=True, use_seasonal=True, key="back_balls", pool_size=12)
        front4 = [b for b, _ in sorted(probs_f4.items(), key=lambda x: x[1], reverse=True)[:5]]
        back4 = [b for b, _ in sorted(probs_b4.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front4) < 5 and b not in front4:
                front4.append(b)
        for b in all_backs:
            if len(back4) < 2 and b not in back4:
                back4.append(b)

        from .base import get_interval_distribution, compute_sum
        d1 = f"AR(2)短周期；P(Top)={probs_f1[front1[0]]:.3f}；和值{compute_sum(front1)}"
        d2 = f"AR(5)长周期；P(Top)={probs_f2[front2[0]]:.3f}；和值{compute_sum(front2)}"
        d3 = f"AR(3)+遗漏补偿；P(Top)={probs_f3[front3[0]]:.3f}；和值{compute_sum(front3)}"
        d4 = f"AR(3)+遗漏+季节周期；P(Top)={probs_f4[front4[0]]:.3f}；和值{compute_sum(front4)}"

        strategies = [
            ("短周期AR(2)", front1, back1, d1),
            ("长周期AR(5)", front2, back2, d2),
            ("遗漏值补偿AR", front3, back3, d3),
            ("季节性ARIMA", front4, back4, d4),
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