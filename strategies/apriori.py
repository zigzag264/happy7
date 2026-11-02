# -*- coding: utf-8 -*-
"""
⑦ 关联规则挖掘 Apriori 预测模型 (v2)

v2 变化:
  - 用“平滑共现概率”替代离散规则 + 01-05 兜底
  - 频繁项集设置最低支持度(>=3 次)，无匹配时回退到基础频率
  - 后区三种策略独立建模，不再共用同一个后区列表
  - 新增前区→后区跨区条件概率
  - 输出 3 种可区分策略:共现平滑 / 频繁项集 / 跨区规则
"""

from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, List, Tuple

from .base import (
    BaseStrategy, format_ball, sort_balls,
    get_interval_distribution, compute_parity, compute_sum,
    validate_prediction_group,
)


class AprioriStrategy(BaseStrategy):
    """关联规则挖掘 Apriori 预测模型 v2"""

    MODEL_ID = "apriori-rules"
    MODEL_NAME = "关联规则Apriori"
    MODEL_TYPE = "ml"

    DECAY = 0.95          # 越新的开奖权重越高
    MIN_PAIR_COUNT = 3    # 2-项集最低出现次数
    PAIR_ALPHA = 2.0      # 共现平滑系数

    @staticmethod
    def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
        total = sum(max(v, 0.0) for v in scores.values())
        if total <= 0:
            n = max(len(scores), 1)
            return {k: 1.0 / n for k in scores}
        return {k: max(v, 0.0) / total for k, v in scores.items()}

    def _weighted_stats(self, data: List[Dict], key: str, pool_size: int):
        """带时间衰减的 base / pair / anchor 计数（data 为 newest-first）"""
        base_counts = Counter()
        anchor_counts = Counter()
        pair_counts = defaultdict(float)
        total_weight = 0.0

        for idx, draw in enumerate(data):
            weight = self.DECAY ** idx
            items = set(draw.get(key, []))
            total_weight += weight
            for b in items:
                base_counts[b] += weight
            for a in items:
                anchor_counts[a] += weight
                for b in items:
                    if a != b:
                        pair_counts[(a, b)] += weight

        balls = [format_ball(i) for i in range(1, pool_size + 1)]
        denom = total_weight if total_weight > 0 else 1.0
        base = {b: base_counts.get(b, 0.0) / denom for b in balls}
        return base, pair_counts, anchor_counts, denom

    def _frequency_scores(self, base) -> Dict[str, float]:
        return self._normalize(base)

    def _cooccurrence_scores(self, base, pair_counts, anchor_counts,
                             anchors, pool_size) -> Dict[str, float]:
        """P(候选球 | 上期锚点球) 的平滑平均"""
        balls = [format_ball(i) for i in range(1, pool_size + 1)]
        scores = {}
        for b in balls:
            total = 0.0
            for x in anchors:
                if x == b:
                    continue
                cx = anchor_counts.get(x, 0.0)
                cxb = pair_counts.get((x, b), 0.0)
                cond = ((cxb + self.PAIR_ALPHA * base[b]) / (cx + self.PAIR_ALPHA)
                        if cx + self.PAIR_ALPHA > 0 else base[b])
                total += cond
            scores[b] = total / max(len(anchors), 1)
        return self._normalize(scores)

    def _frequent_pair_scores(self, data: List[Dict], key: str, pool_size: int,
                              last_items: List[str]) -> Tuple[Dict[str, float], int]:
        """频繁 2-项集：支持度 >= MIN_PAIR_COUNT，按 support × lift 加权"""
        n = max(len(data), 1)
        item_counts = Counter()
        pair_counts = Counter()

        for draw in data:
            items = sorted(set(draw.get(key, [])))
            for item in items:
                item_counts[item] += 1
            for a, b in combinations(items, 2):
                pair_counts[(a, b)] += 1

        base = {format_ball(i): item_counts.get(format_ball(i), 0) / n
                for i in range(1, pool_size + 1)}
        scores = dict(base)
        last_set = set(last_items)
        matched = 0

        for (a, b), count in pair_counts.items():
            if count < self.MIN_PAIR_COUNT:
                continue
            support = count / n
            base_a = max(base.get(a, 0.0), 1e-9)
            base_b = max(base.get(b, 0.0), 1e-9)
            lift = min(support / (base_a * base_b), 3.0)
            if a in last_set:
                scores[b] = scores.get(b, 0.0) + support * lift
                matched += 1
            if b in last_set:
                scores[a] = scores.get(a, 0.0) + support * lift
                matched += 1

        return self._normalize(scores), matched

    def _cross_zone_scores(self, data: List[Dict], last_fronts: List[str],
                           pool_size: int = 12) -> Dict[str, float]:
        """前区上期号码 → 后区候选球的平滑条件概率"""
        base_counts = Counter()
        front_counts = Counter()
        pair_counts = defaultdict(float)
        total_weight = 0.0

        for idx, draw in enumerate(data):
            weight = self.DECAY ** idx
            total_weight += weight
            fronts = set(draw.get("front_balls", []))
            backs = set(draw.get("back_balls", []))
            for b in backs:
                base_counts[b] += weight
            for f in fronts:
                front_counts[f] += weight
                for b in backs:
                    pair_counts[(f, b)] += weight

        denom = total_weight if total_weight > 0 else 1.0
        balls = [format_ball(i) for i in range(1, pool_size + 1)]
        base = {b: base_counts.get(b, 0.0) / denom for b in balls}
        alpha = 1.0
        scores = {}
        for b in balls:
            total = 0.0
            for f in last_fronts:
                cf = front_counts.get(f, 0.0)
                cfb = pair_counts.get((f, b), 0.0)
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
        return AprioriStrategy._normalize(result)

    @staticmethod
    def _pick_top(scores, count):
        return [b for b, _ in sorted(scores.items(), key=lambda kv: (-kv[1], int(kv[0])))[:count]]

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

        last_draw = data[0]  # newest-first
        last_fronts = last_draw.get("front_balls", [])
        last_backs = last_draw.get("back_balls", [])

        front_base, front_pairs, front_anchors, _ = self._weighted_stats(
            data, "front_balls", 35)
        back_base, back_pairs, back_anchors, _ = self._weighted_stats(
            data, "back_balls", 12)

        front_freq = self._frequency_scores(front_base)
        back_freq = self._frequency_scores(back_base)
        front_co = self._cooccurrence_scores(
            front_base, front_pairs, front_anchors, last_fronts, 35)
        back_co = self._cooccurrence_scores(
            back_base, back_pairs, back_anchors, last_backs, 12)
        front_pairs_scores, front_matched = self._frequent_pair_scores(
            data, "front_balls", 35, last_fronts)
        back_pairs_scores, back_matched = self._frequent_pair_scores(
            data, "back_balls", 12, last_backs)
        back_cross = self._cross_zone_scores(data, last_fronts, 12)

        front_maps = [
            self._blend({"freq": front_freq, "co": front_co}, {"freq": 0.35, "co": 0.65}),
            front_pairs_scores,
            self._blend({"freq": front_freq, "co": front_co}, {"freq": 0.50, "co": 0.50}),
        ]
        back_maps = [
            self._blend({"freq": back_freq, "co": back_co}, {"freq": 0.45, "co": 0.55}),
            self._blend({"freq": back_freq, "pairs": back_pairs_scores},
                        {"freq": 0.50, "pairs": 0.50}),
            self._blend({"freq": back_freq, "cross": back_cross},
                        {"freq": 0.30, "cross": 0.70}),
        ]

        front_sets = [self._pick_top(m, 5) for m in front_maps]
        back_sets = [self._pick_top(m, 2) for m in back_maps]
        front_sets = self._distinct_sets(front_sets, front_maps, 5)
        back_sets = self._distinct_sets(back_sets, back_maps, 2)

        details = [
            "v2 平滑共现规则(衰减0.95, alpha=2.0；前区0.35频率+0.65共现)",
            f"v2 频繁项集规则(2-项集>=3次；前区匹配{front_matched}条)",
            "v2 跨区关联规则(前区0.50频率+0.50共现；后区前→后跨区0.70)",
        ]
        names = ["共现平滑规则", "频繁项集规则", "跨区关联规则"]

        predictions = []
        for i, (fronts, backs, detail) in enumerate(
                zip(front_sets, back_sets, details), 1):
            desc = (f"{detail}；和值{compute_sum(fronts)}；"
                    f"奇偶{compute_parity(fronts)}；区间{get_interval_distribution(fronts)}")
            pred = {
                "group_id": i,
                "strategy": names[i - 1],
                "front_balls": sort_balls(fronts),
                "back_balls": sort_balls(backs),
                "description": desc,
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)
