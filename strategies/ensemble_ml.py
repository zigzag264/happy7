# -*- coding: utf-8 -*-
"""
⑤ 机器学习集成预测模型 (v2)
Random Forest 分类器预测每个号码的出现概率

v2 修复:
  - 历史数据按时间升序构造特征/标签(此前 newest-first 被当成了 oldest-first)
  - 所有号码池化训练,样本量从 ~25/号码 提升到 ~700
  - 分位数阈值控制树的分裂候选,纯 Python 下可跑
  - 按期号生成随机种子,避免跨期重复
  - 输出 3 种可区分的策略:纯 RF / 概率校准 / 近期加权
"""

import math
import random
from typing import List, Dict, Tuple

from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    get_interval, get_interval_distribution, compute_parity, compute_sum,
    to_chronological, draw_seed, validate_prediction_group,
)


class SimpleTree:
    """简化版决策树(分位数阈值 + 平滑叶子概率)"""

    def __init__(self, max_depth=4, min_samples=3, max_thresholds=12):
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.max_thresholds = max_thresholds
        self.tree = None

    @staticmethod
    def _gini(labels):
        if not labels:
            return 0.0
        pos = sum(labels)
        n = len(labels)
        p = pos / n
        return 1.0 - p * p - (1 - p) * (1 - p)

    def _candidate_thresholds(self, values):
        if len(values) <= 1:
            return []
        if len(values) <= self.max_thresholds + 1:
            return [(values[i] + values[i + 1]) / 2 for i in range(len(values) - 1)]
        step = (len(values) - 1) / (self.max_thresholds + 1)
        idxs = sorted({max(1, min(len(values) - 1, int(round(step * i))))
                       for i in range(1, self.max_thresholds + 1)})
        return [values[i] for i in idxs]

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

    def _leaf(self, y):
        # 拉普拉斯平滑，避免 0/1 极端概率
        return (sum(y) + 1.0) / (len(y) + 2.0)

    def _build(self, X, y, depth):
        if depth >= self.max_depth or len(X) < self.min_samples:
            return {"leaf": True, "prob": self._leaf(y)}

        best_gain = 0.0
        best_partition = None
        best_feature = 0
        best_threshold = 0.0
        base_gini = self._gini(y)
        n_features = len(X[0]) if X else 0

        for feature_idx in range(n_features):
            values = sorted({X[i][feature_idx] for i in range(len(X))})
            for threshold in self._candidate_thresholds(values):
                left_x, left_y, right_x, right_y = self._split(X, y, feature_idx, threshold)
                if not left_y or not right_y:
                    continue
                weighted = (len(left_y) / len(y) * self._gini(left_y)
                            + len(right_y) / len(y) * self._gini(right_y))
                gain = base_gini - weighted
                if gain > best_gain:
                    best_gain = gain
                    best_partition = (left_x, left_y, right_x, right_y)
                    best_feature = feature_idx
                    best_threshold = threshold

        if best_gain < 0.005 or best_partition is None:
            return {"leaf": True, "prob": self._leaf(y)}

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
    """简化版随机森林(局部随机数,可复现)"""

    def __init__(self, n_estimators=24, max_depth=5, min_samples=3,
                 max_features=None, max_thresholds=12, seed=0):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.max_features = max_features
        self.max_thresholds = max_thresholds
        self.seed = seed
        self.trees = []

    def fit(self, X, y):
        rng = random.Random(self.seed)
        n_samples = len(X)
        n_features = len(X[0]) if X else 0
        if self.max_features is None:
            self.max_features = max(1, int(math.sqrt(n_features)))

        for _ in range(self.n_estimators):
            indices = [rng.randint(0, n_samples - 1) for _ in range(n_samples)]
            X_boot = [X[i] for i in indices]
            y_boot = [y[i] for i in indices]
            features = rng.sample(range(n_features), min(self.max_features, n_features))
            X_sub = [[x[f] for f in features] for x in X_boot]
            tree = SimpleTree(
                max_depth=self.max_depth,
                min_samples=self.min_samples,
                max_thresholds=self.max_thresholds,
            )
            tree.fit(X_sub, y_boot)
            self.trees.append((features, tree))
        return self

    def predict_proba(self, x):
        if not self.trees:
            return 0.0
        probs = []
        for features, tree in self.trees:
            probs.append(tree.predict_proba([x[f] for f in features]))
        return sum(probs) / len(probs)


class EnsembleMLStrategy(BaseStrategy):
    """机器学习集成预测模型 v2"""

    MODEL_ID = "ensemble-ml"
    MODEL_NAME = "随机森林集成"
    MODEL_TYPE = "ml"

    WINDOWS = (5, 10, 20)
    MIN_HISTORY = 10

    # ---------- 特征 ----------

    def _missing_count(self, chrono, ball, key):
        miss = 0
        for draw in reversed(chrono):
            if ball in draw.get(key, []):
                break
            miss += 1
        return miss

    def _features_at(self, chrono, end, ball, key, pool_size):
        """用 chrono[:end] 的信息构造号码特征（end 为预测期的下标）"""
        freqs = {}
        for window in self.WINDOWS:
            start = max(0, end - window)
            span = end - start
            count = sum(1 for d in chrono[start:end] if ball in d.get(key, []))
            freqs[window] = count / span if span else 0.0

        total_count = sum(1 for d in chrono[:end] if ball in d.get(key, []))
        total_rate = total_count / end if end else 0.0
        missing = self._missing_count(chrono[:end], ball, key)

        last1 = 1.0 if end >= 1 and ball in chrono[end - 1].get(key, []) else 0.0
        last2 = 1.0 if end >= 2 and ball in chrono[end - 2].get(key, []) else 0.0

        return [
            int(ball) / pool_size,
            get_interval(ball) / 2.0 if pool_size == 35 else 0.0,
            int(ball) % 2,
            freqs[5], freqs[10], freqs[20],
            total_rate,
            min(missing, 20) / 20.0,
            freqs[5] - freqs[20],
            last1, last2,
        ]

    def _build_samples(self, chrono, key, pool_size):
        X, y = [], []
        for end in range(self.MIN_HISTORY, len(chrono)):
            for i in range(1, pool_size + 1):
                ball = format_ball(i)
                X.append(self._features_at(chrono, end, ball, key, pool_size))
                y.append(1 if ball in chrono[end].get(key, []) else 0)
        return X, y

    # ---------- 概率 ----------

    @staticmethod
    def _normalize(scores):
        total = sum(max(v, 0.0) for v in scores.values())
        if total <= 0:
            n = max(len(scores), 1)
            return {k: 1.0 / n for k in scores}
        return {k: max(v, 0.0) / total for k, v in scores.items()}

    def _frequency_scores(self, chrono, key, pool_size, window=None):
        data = chrono[-window:] if window else chrono
        counts = compute_frequency(data, pool_size, key)
        return self._normalize(counts)

    def _omission_scores(self, chrono, key, pool_size):
        scores = {}
        for i in range(1, pool_size + 1):
            ball = format_ball(i)
            scores[ball] = self._missing_count(chrono, ball, key) + 1.0
        return self._normalize(scores)

    def _predict_probs(self, chrono, key, pool_size, n_estimators,
                       max_depth, max_thresholds, seed):
        X, y = self._build_samples(chrono, key, pool_size)
        if len(X) < 30 or len(set(y)) < 2:
            return self._frequency_scores(chrono, key, pool_size)

        forest = SimpleRandomForest(
            n_estimators=n_estimators,
            max_depth=max_depth,
            max_thresholds=max_thresholds,
            seed=seed,
        ).fit(X, y)

        probs = {}
        for i in range(1, pool_size + 1):
            ball = format_ball(i)
            probs[ball] = forest.predict_proba(
                self._features_at(chrono, len(chrono), ball, key, pool_size)
            )
        if max(probs.values()) - min(probs.values()) < 1e-9:
            return self._frequency_scores(chrono, key, pool_size)
        return self._normalize(probs)

    # ---------- 选号 ----------

    @staticmethod
    def _pick_top(scores, count):
        return [b for b, _ in sorted(scores.items(), key=lambda kv: (-kv[1], int(kv[0])))[:count]]

    @staticmethod
    def _distinct_sets(sets, score_maps, count):
        """避免三种策略给出完全相同的号码组合"""
        seen = set()
        out = []
        for picks, scores in zip(sets, score_maps):
            picks = sort_balls(picks)
            key = tuple(picks)
            if key in seen:
                candidates = [b for b in sorted(scores, key=lambda x: (-scores[x], int(x)))
                              if b not in picks]
                for candidate in candidates:
                    new_picks = sort_balls(picks[:-1] + [candidate])
                    if tuple(new_picks) not in seen:
                        picks = new_picks
                        key = tuple(new_picks)
                        break
            seen.add(key)
            out.append(picks)
        return out

    # ---------- 主流程 ----------

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        chrono = to_chronological(data)
        seed_base = draw_seed(self.target_period, self.seed_salt)

        # 三种 RF 变体：默认 / 强正则(浅树) / 深度树。
        # 共用池化特征，但不同深度与阈值数量，保证策略有真实差异。
        configs = [
            (24, 5, 12, 11, 23),
            (20, 3, 8, 31, 43),
            (24, 4, 10, 51, 63),
        ]
        front_maps, back_maps = [], []
        for n_estimators, depth, thresholds, front_salt, back_salt in configs:
            front_maps.append(self._predict_probs(
                chrono, "front_balls", 35, n_estimators=n_estimators,
                max_depth=depth, max_thresholds=thresholds,
                seed=seed_base + front_salt,
            ))
            back_maps.append(self._predict_probs(
                chrono, "back_balls", 12, n_estimators=n_estimators,
                max_depth=depth, max_thresholds=thresholds,
                seed=seed_base + back_salt,
            ))

        front_sets = [self._pick_top(m, 5) for m in front_maps]

        # 后区只有 12 个号码，纯池化 RF 容易过拟合；与长期/近期频率、
        # 遗漏做适度融合，保住旧版后区命中水平。
        back_long = self._frequency_scores(chrono, "back_balls", 12)
        back_recent10 = self._frequency_scores(chrono, "back_balls", 12, window=10)
        back_omit = self._omission_scores(chrono, "back_balls", 12)
        back_blends = [
            (0.60, 0.40, 0.0, 0.0),
            (0.60, 0.20, 0.20, 0.0),
            (0.50, 0.30, 0.0, 0.20),
        ]
        blended_backs = []
        for rf, (w_rf, w_long, w_recent, w_omit) in zip(back_maps, back_blends):
            blended_backs.append({
                b: (w_rf * rf[b] + w_long * back_long[b]
                    + w_recent * back_recent10[b] + w_omit * back_omit[b])
                for b in rf
            })
        back_maps = blended_backs

        back_sets = [self._pick_top(m, 2) for m in back_maps]
        front_sets = self._distinct_sets(front_sets, front_maps, 5)
        back_sets = self._distinct_sets(back_sets, back_maps, 2)

        details = [
            "v2 时序池化RF(默认:24树/depth5/12阈值)；后区0.6RF+0.4长期",
            "v2 时序池化RF(强正则:20树/depth3/8阈值)；后区0.6RF+0.2长期+0.2近10",
            "v2 时序池化RF(均衡:24树/depth4/10阈值)；后区0.5RF+0.3长期+0.2遗漏",
        ]
        names = ["RF时序池化", "RF正则池化", "RF均衡池化"]
        strategies = []
        for i, (fronts, backs, detail) in enumerate(
                zip(front_sets, back_sets, details), 1):
            prob = max(front_maps[i - 1].values())
            desc = (f"{detail}；P(Top)={prob:.3f}；和值{compute_sum(fronts)}；"
                    f"奇偶{compute_parity(fronts)}；区间{get_interval_distribution(fronts)}")
            strategies.append((i, names[i - 1], fronts, backs, desc))

        predictions = []
        for gid, name, fronts, backs, desc in strategies:
            pred = {
                "group_id": gid,
                "strategy": name,
                "front_balls": sort_balls(fronts),
                "back_balls": sort_balls(backs),
                "description": desc,
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)
