# -*- coding: utf-8 -*-
"""
④ 蒙特卡洛模拟预测模型 (v2)

v2 变化:
  - 不再“反复采样取众数”，而是按概率分布直接加权采样一次
  - 去掉和值/奇偶硬过滤，改为长期频率 + 近期频率 + 遗漏 + 共现的概率融合
  - 按期号生成随机种子，避免固定 seed(42) 导致跨期重复
  - 3 种策略使用不同权重组合，并保证号码组合有区分度
"""

import random
from collections import Counter, defaultdict
from typing import Dict, List

from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency, compute_missing,
    get_interval_distribution, compute_parity, compute_sum,
    to_chronological, draw_seed, validate_prediction_group,
)


class MonteCarloStrategy(BaseStrategy):
    """蒙特卡洛模拟预测模型 v2"""

    MODEL_ID = "monte-carlo"
    MODEL_NAME = "蒙特卡洛模拟"
    MODEL_TYPE = "statistical"

    @staticmethod
    def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
        total = sum(max(v, 0.0) for v in scores.values())
        if total <= 0:
            n = max(len(scores), 1)
            return {k: 1.0 / n for k in scores}
        return {k: max(v, 0.0) / total for k, v in scores.items()}

    def _frequency_scores(self, chrono, key, pool_size, window=None):
        data = chrono[-window:] if window else chrono
        return self._normalize(compute_frequency(data, pool_size, key))

    def _omission_scores(self, chrono, key, pool_size):
        # compute_missing 期望 newest-first
        missing = compute_missing(list(reversed(chrono)), pool_size, key)
        return self._normalize({b: m + 1.0 for b, m in missing.items()})

    def _cooccurrence_scores(self, chrono, key, pool_size, anchors):
        """P(候选球 | 上期锚点球) 的平滑平均，锚点为空时回退频率"""
        n = max(len(chrono), 1)
        base_counts = Counter()
        pair_counts = defaultdict(int)
        anchor_counts = Counter()

        for draw in chrono:
            items = set(draw.get(key, []))
            for b in items:
                base_counts[b] += 1
            for x in items:
                anchor_counts[x] += 1
                for b in items:
                    if x != b:
                        pair_counts[(x, b)] += 1

        balls = [format_ball(i) for i in range(1, pool_size + 1)]
        base = {b: base_counts.get(b, 0) / n for b in balls}
        alpha = 2.0
        scores = {}
        for b in balls:
            total = 0.0
            for x in anchors:
                if x == b:
                    continue
                cx = anchor_counts.get(x, 0)
                cxb = pair_counts.get((x, b), 0)
                cond = (cxb + alpha * base[b]) / (cx + alpha) if cx + alpha > 0 else base[b]
                total += cond
            scores[b] = total / max(len(anchors), 1)
        return self._normalize(scores)

    def _cross_zone_scores(self, chrono, last_fronts, pool_size=12):
        """前区上期号码 -> 后区候选球的平滑条件概率"""
        n = max(len(chrono), 1)
        base_counts = Counter()
        front_counts = Counter()
        pair_counts = defaultdict(int)

        for draw in chrono:
            fronts = set(draw.get("front_balls", []))
            backs = set(draw.get("back_balls", []))
            for b in backs:
                base_counts[b] += 1
            for f in fronts:
                front_counts[f] += 1
                for b in backs:
                    pair_counts[(f, b)] += 1

        balls = [format_ball(i) for i in range(1, pool_size + 1)]
        base = {b: base_counts.get(b, 0) / n for b in balls}
        alpha = 1.0
        scores = {}
        for b in balls:
            total = 0.0
            for f in last_fronts:
                cf = front_counts.get(f, 0)
                cfb = pair_counts.get((f, b), 0)
                cond = (cfb + alpha * base[b]) / (cf + alpha) if cf + alpha > 0 else base[b]
                total += cond
            scores[b] = total / max(len(last_fronts), 1)
        return self._normalize(scores)

    @staticmethod
    def _blend(maps, weights):
        base_map = next(iter(maps.values()))
        result = {b: 0.0 for b in base_map}
        for name, weight in weights.items():
            for b, value in maps[name].items():
                result[b] += weight * value
        return MonteCarloStrategy._normalize(result)

    @staticmethod
    def _sample(rng, scores, count, sharpen=1.0):
        candidates = list(scores.keys())
        weights = [max(scores[b], 1e-12) ** sharpen for b in candidates]
        picks = []
        for _ in range(count):
            ball = rng.choices(candidates, weights=weights, k=1)[0]
            idx = candidates.index(ball)
            candidates.pop(idx)
            weights.pop(idx)
            picks.append(ball)
        return sort_balls(picks)

    @staticmethod
    def _distinct_sets(sets, score_maps, count):
        seen = set()
        out = []
        for picks, scores in zip(sets, score_maps):
            picks = sort_balls(picks)
            key = tuple(picks)
            if key in seen:
                ranked = [b for b in sorted(scores, key=lambda x: (-scores[x], int(x)))
                          if b not in picks]
                for candidate in ranked:
                    new_picks = sort_balls(picks[:-1] + [candidate])
                    if tuple(new_picks) not in seen:
                        picks = new_picks
                        key = tuple(new_picks)
                        break
            seen.add(key)
            out.append(picks)
        return out

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        chrono = to_chronological(data)
        last_draw = data[0]  # newest-first 的第一条就是上期
        last_fronts = last_draw.get("front_balls", [])
        last_backs = last_draw.get("back_balls", [])

        front_maps = {
            "long": self._frequency_scores(chrono, "front_balls", 35),
            "recent": self._frequency_scores(chrono, "front_balls", 35, window=10),
            "omit": self._omission_scores(chrono, "front_balls", 35),
            "co": self._cooccurrence_scores(chrono, "front_balls", 35, last_fronts),
        }
        back_maps = {
            "long": self._frequency_scores(chrono, "back_balls", 12),
            "recent": self._frequency_scores(chrono, "back_balls", 12, window=10),
            "omit": self._omission_scores(chrono, "back_balls", 12),
            "co": self._cooccurrence_scores(chrono, "back_balls", 12, last_backs),
            "cross": self._cross_zone_scores(chrono, last_fronts, 12),
        }

        configs = [
            {
                "name": "MC热号概率",
                "front": {"long": 0.45, "recent": 0.30, "co": 0.25},
                "back": {"long": 0.45, "recent": 0.30, "omit": 0.25},
                "salt": 101,
                "detail": "v2 热号概率(长期0.45/近10期0.30/共现0.25)",
            },
            {
                "name": "MC遗漏回归",
                "front": {"long": 0.35, "recent": 0.15, "omit": 0.50},
                "back": {"long": 0.35, "recent": 0.15, "omit": 0.50},
                "salt": 202,
                "detail": "v2 遗漏回归(长期0.35/近10期0.15/遗漏0.50)",
            },
            {
                "name": "MC共现融合",
                "front": {"long": 0.30, "recent": 0.20, "omit": 0.10, "co": 0.40},
                "back": {"long": 0.25, "recent": 0.20, "omit": 0.20, "cross": 0.35},
                "salt": 303,
                "detail": "v2 共现融合(前区0.30/0.20/0.10/0.40；后区跨区共现)",
            },
        ]

        front_scores, back_scores = [], []
        front_sets, back_sets = [], []
        for cfg in configs:
            f_scores = self._blend(front_maps, cfg["front"])
            b_scores = self._blend(back_maps, cfg["back"])
            rng = random.Random(draw_seed(self.target_period, cfg["salt"] + self.seed_salt))
            front_scores.append(f_scores)
            back_scores.append(b_scores)
            front_sets.append(self._sample(rng, f_scores, 5))
            # 后区只有 2 个名额，适当锐化权重，避免纯随机把频率信号冲掉
            back_sets.append(self._sample(rng, b_scores, 2, sharpen=1.5))

        front_sets = self._distinct_sets(front_sets, front_scores, 5)
        back_sets = self._distinct_sets(back_sets, back_scores, 2)

        predictions = []
        for i, (cfg, fronts, backs, f_scores) in enumerate(
                zip(configs, front_sets, back_sets, front_scores), 1):
            desc = (f'{cfg["detail"]}；无硬约束；和值{compute_sum(fronts)}；'
                    f'奇偶{compute_parity(fronts)}；区间{get_interval_distribution(fronts)}')
            pred = {
                "group_id": i,
                "strategy": cfg["name"],
                "front_balls": sort_balls(fronts),
                "back_balls": sort_balls(backs),
                "description": desc,
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)
