# -*- coding: utf-8 -*-
"""
⑤ 机器学习集成预测模型
Random Forest 分类器预测每个号码的出现概率
"""

import math
from collections import defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    compute_missing, validate_prediction_group
)


class SimpleTree:
    """简化版决策树"""

    def __init__(self, max_depth=4, min_samples=3):
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.tree = None

    def _gini(self, labels):
        if not labels:
            return 0.0
        pos = sum(labels)
        n = len(labels)
        p = pos / n
        return 1.0 - p * p - (1 - p) * (1 - p)

    def _split(self, X, y, feature_idx, threshold):
        left_x, left_y, right_x, right_y = [], [], [], []
        for i in range(len(X)):
            if X[i][feature_idx] <= threshold:
                left_x.append(X[i])
                left_y.append(y[i])
            else:
                right_x.append(X[i])
                right_y.append(y[i])
        return left_x, left_y, right_x, right_y

    def _build(self, X, y, depth):
        if depth >= self.max_depth or len(X) < self.min_samples:
            pos = sum(y)
            return {"leaf": True, "prob": pos / max(len(y), 1)}

        best_gain = 0
        best_feature = 0
        best_threshold = 0
        best_partition = None

        n_features = len(X[0]) if X else 0
        base_gini = self._gini(y)

        for feature_idx in range(n_features):
            values = sorted(set(X[i][feature_idx] for i in range(len(X))))
            for i in range(len(values) - 1):
                threshold = (values[i] + values[i + 1]) / 2
                left_x, left_y, right_x, right_y = self._split(X, y, feature_idx, threshold)
                if not left_y or not right_y:
                    continue
                weighted = len(left_y) / len(y) * self._gini(left_y) + \
                           len(right_y) / len(y) * self._gini(right_y)
                gain = base_gini - weighted
                if gain > best_gain:
                    best_gain = gain
                    best_feature = feature_idx
                    best_threshold = threshold
                    best_partition = (left_x, left_y, right_x, right_y)

        if best_gain < 0.01 or best_partition is None:
            pos = sum(y)
            return {"leaf": True, "prob": pos / max(len(y), 1)}

        left_x, left_y, right_x, right_y = best_partition

        return {
            "leaf": False,
            "feature": best_feature,
            "threshold": best_threshold,
            "left": self._build(left_x, left_y, depth + 1),
            "right": self._build(right_x, right_y, depth + 1),
        }

    def fit(self, X, y):
        self.tree = self._build(X, y, 0)
        return self

    def predict_proba(self, x):
        node = self.tree
        while not node["leaf"]:
            if x[node["feature"]] <= node["threshold"]:
                node = node["left"]
            else:
                node = node["right"]
        return node["prob"]


class SimpleRandomForest:
    """简化版随机森林"""

    def __init__(self, n_estimators=30, max_depth=4, min_samples=3, max_features=None):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.max_features = max_features
        self.trees = []

    def fit(self, X, y, feature_importance=None):
        import random
        n_samples = len(X)
        n_features = len(X[0]) if X else 0
        if self.max_features is None:
            self.max_features = max(1, int(math.sqrt(n_features)))

        for _ in range(self.n_estimators):
            # Bootstrap 抽样
            indices = [random.randint(0, n_samples - 1) for _ in range(n_samples)]
            X_boot = [X[i] for i in indices]
            y_boot = [y[i] for i in indices]

            # 特征子集
            features = random.sample(range(n_features), self.max_features)
            X_sub = [[x[f] for f in features] for x in X_boot]

            tree = SimpleTree(max_depth=self.max_depth, min_samples=self.min_samples)
            tree.fit(X_sub, y_boot)
            self.trees.append((features, tree))

        return self

    def predict_proba(self, x):
        probs = []
        for features, tree in self.trees:
            x_sub = [x[f] for f in features]
            probs.append(tree.predict_proba(x_sub))
        return sum(probs) / len(probs)


class EnsembleMLStrategy(BaseStrategy):
    """机器学习集成预测模型"""

    MODEL_ID = "ensemble-ml"
    MODEL_NAME = "随机森林集成"
    MODEL_TYPE = "ml"

    def _build_features_sequences(self, data: List[Dict], key: str,
                                   pool_size: int) -> Tuple[List[List[float]], List[List[int]]]:
        """构建特征序列和标签"""
        all_X = []
        all_y = []

        for t in range(5, len(data)):
            X = []
            y = []
            for i in range(1, pool_size + 1):
                ball = format_ball(i)

                # 特征
                features = []
                # 最近5/10/20期的频率
                for period in [5, 10, 20]:
                    window = data[t-period:t]
                    freq = sum(1 for d in window if ball in d.get(key, []))
                    features.append(freq / period)

                # 当前遗漏期数
                miss = 0
                for d in data[t-1::-1]:
                    if ball in d.get(key, []):
                        break
                    miss += 1
                features.append(min(miss / 20, 1.0))

                # 总体频率
                total_freq = sum(1 for d in data[:t] if ball in d.get(key, []))
                features.append(total_freq / max(t, 1))

                # 近期趋势
                recent_freq = sum(1 for d in data[t-5:t] if ball in d.get(key, []))
                features.append(recent_freq / 5 - total_freq / max(t, 1))

                # 上期是否出现
                features.append(1.0 if data[t-1].get(key) and ball in data[t-1].get(key) else 0.0)

                # 上上期
                features.append(1.0 if t >= 2 and data[t-2].get(key) and ball in data[t-2].get(key) else 0.0)

                X.append(features)

                # 标签
                label = 1 if ball in data[t].get(key, []) else 0
                y.append(label)

            all_X.append(X)
            all_y.append(y)

        return all_X, all_y

    def _predict_probs(self, data: List[Dict], key: str, pool_size: int,
                        n_estimators: int = 30, max_depth: int = 4) -> Tuple[Dict[str, float], str]:
        """训练并预测每个号码的概率"""
        all_X, all_y = self._build_features_sequences(data, key, pool_size)
        if not all_X:
            return {format_ball(i): 0.1 for i in range(1, pool_size + 1)}, "数据不足"

        import random
        random.seed(42)

        # 使用最后一个样本的特征作为预测输入
        X_train = all_X[:-1] if len(all_X) > 1 else all_X
        y_train = all_y[:-1] if len(all_y) > 1 else all_y

        # 展平
        X_flat = [x for sample in X_train for x in sample]
        y_flat = [l for sample in y_train for l in sample]

        # 特征索引到号码的映射
        n_features_per_ball = len(X_flat[0]) if X_flat else 7

        # 为每个号码训练一个分类器
        probs = {}
        for ball_idx in range(pool_size):
            # 提取该号码的所有样本
            X_ball = [X_flat[j] for j in range(ball_idx, len(X_flat), pool_size)]
            y_ball = [y_flat[j] for j in range(ball_idx, len(y_flat), pool_size)]

            if len(X_ball) < 5:
                probs[format_ball(ball_idx + 1)] = 0.1
                continue

            rf = SimpleRandomForest(
                n_estimators=n_estimators,
                max_depth=max_depth,
                min_samples=3
            )
            rf.fit(X_ball, y_ball)

            # 预测：用最新特征
            latest_X = X_ball[-1]
            probs[format_ball(ball_idx + 1)] = rf.predict_proba(latest_X)

        return probs, f"RF({n_estimators}树, depth={max_depth})"

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        # 4 组策略
        # 1. 默认参数
        probs_f1, model_desc1 = self._predict_probs(data, "front_balls", 35,
                                                     n_estimators=30, max_depth=4)
        probs_b1, _ = self._predict_probs(data, "back_balls", 12,
                                           n_estimators=20, max_depth=3)
        front1 = [b for b, _ in sorted(probs_f1.items(), key=lambda x: x[1], reverse=True)[:5]]
        back1 = [b for b, _ in sorted(probs_b1.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front1) < 5 and b not in front1:
                front1.append(b)
        for b in all_backs:
            if len(back1) < 2 and b not in back1:
                back1.append(b)

        # 2. 强正则化（浅树）
        probs_f2, model_desc2 = self._predict_probs(data, "front_balls", 35,
                                                     n_estimators=20, max_depth=2)
        probs_b2, _ = self._predict_probs(data, "back_balls", 12,
                                           n_estimators=15, max_depth=2)
        front2 = [b for b, _ in sorted(probs_f2.items(), key=lambda x: x[1], reverse=True)[:5]]
        back2 = [b for b, _ in sorted(probs_b2.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front2) < 5 and b not in front2:
                front2.append(b)
        for b in all_backs:
            if len(back2) < 2 and b not in back2:
                back2.append(b)

        # 3. 深树
        probs_f3, model_desc3 = self._predict_probs(data, "front_balls", 35,
                                                     n_estimators=40, max_depth=6)
        probs_b3, _ = self._predict_probs(data, "back_balls", 12,
                                           n_estimators=25, max_depth=4)
        front3 = [b for b, _ in sorted(probs_f3.items(), key=lambda x: x[1], reverse=True)[:5]]
        back3 = [b for b, _ in sorted(probs_b3.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front3) < 5 and b not in front3:
                front3.append(b)
        for b in all_backs:
            if len(back3) < 2 and b not in back3:
                back3.append(b)

        # 4. 概率加权（结合频率）
        front_freq = compute_frequency(data, 35, "front_balls")
        back_freq = compute_frequency(data, 12, "back_balls")
        probs_f4 = {}
        for i in range(1, 36):
            b = format_ball(i)
            probs_f4[b] = probs_f1.get(b, 0.1) * 0.7 + (front_freq.get(b, 0) / max(len(data), 1)) * 0.3
        probs_b4 = {}
        for i in range(1, 13):
            b = format_ball(i)
            probs_b4[b] = probs_b1.get(b, 0.1) * 0.7 + (back_freq.get(b, 0) / max(len(data), 1)) * 0.3
        front4 = [b for b, _ in sorted(probs_f4.items(), key=lambda x: x[1], reverse=True)[:5]]
        back4 = [b for b, _ in sorted(probs_b4.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_fronts:
            if len(front4) < 5 and b not in front4:
                front4.append(b)
        for b in all_backs:
            if len(back4) < 2 and b not in back4:
                back4.append(b)

        from .base import get_interval_distribution, compute_sum
        d1 = f"{model_desc1}；P(Top)={probs_f1[front1[0]]:.3f}；和值{compute_sum(front1)}"
        d2 = f"{model_desc2}；P(Top)={probs_f2[front2[0]]:.3f}；和值{compute_sum(front2)}"
        d3 = f"{model_desc3}；P(Top)={probs_f3[front3[0]]:.3f}；和值{compute_sum(front3)}"
        d4 = f"RF+freq加权(0.7/0.3)；P(Top)={probs_f4[front4[0]]:.3f}；和值{compute_sum(front4)}"

        strategies = [
            ("RF默认参数", front1, back1, d1),
            ("RF强正则化", front2, back2, d2),
            ("RF深度树", front3, back3, d3),
            ("RF概率加权", front4, back4, d4),
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