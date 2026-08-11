# -*- coding: utf-8 -*-
"""
⑦ 关联规则挖掘 Apriori 预测模型
挖掘频繁项集和关联规则，发现号码共现规律
"""

from collections import defaultdict, Counter
from itertools import combinations
from typing import List, Dict, Set, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    validate_prediction_group
)


class AprioriStrategy(BaseStrategy):
    """关联规则挖掘 Apriori 预测模型"""

    MODEL_ID = "apriori-rules"
    MODEL_NAME = "关联规则Apriori"
    MODEL_TYPE = "ml"

    def _get_itemsets(self, data: List[Dict], key: str, min_support: float) -> Dict[Tuple[str, ...], float]:
        """获取频繁项集"""
        n = len(data)
        transactions = [set(d.get(key, [])) for d in data]

        # 1-项集
        item_counts = Counter()
        for t in transactions:
            for item in t:
                item_counts[item] += 1

        freq_1 = {tuple([item]): count / n
                  for item, count in item_counts.items()
                  if count / n >= min_support}

        if not freq_1:
            # 放宽支持度
            freq_1 = {tuple([item]): count / n
                      for item, count in item_counts.most_common(10)}

        # 2-项集
        freq_2 = {}
        item_list = list(set(item for itemset in freq_1 for item in itemset))
        for pair in combinations(item_list, 2):
            count = sum(1 for t in transactions if pair[0] in t and pair[1] in t)
            support = count / n
            if support >= min_support * 0.5:
                freq_2[tuple(sorted(pair))] = support

        # 3-项集
        freq_3 = {}
        item_list_2 = list(set(item for itemset in freq_2 for item in itemset))
        for triple in combinations(item_list_2, 3):
            count = sum(1 for t in transactions if all(item in t for item in triple))
            support = count / n
            if support >= min_support * 0.3:
                freq_3[tuple(sorted(triple))] = support

        return freq_1, freq_2, freq_3, transactions

    def _generate_rules(self, freq_itemsets: Dict[Tuple[str, ...], float],
                         transactions: List[Set[str]],
                         n: int) -> List[Dict]:
        """从频繁项集生成关联规则"""
        rules = []
        for itemset, support in freq_itemsets.items():
            if len(itemset) < 2:
                continue
            for i in range(1, len(itemset)):
                for antecedent in combinations(itemset, i):
                    consequent = tuple(item for item in itemset if item not in antecedent)
                    if not consequent:
                        continue

                    # 置信度
                    ant_count = sum(1 for t in transactions if all(item in t for item in antecedent))
                    if ant_count == 0:
                        continue
                    confidence = support * n / ant_count

                    # 提升度
                    cons_count = sum(1 for t in transactions if all(item in t for item in consequent))
                    if cons_count == 0:
                        continue
                    lift = confidence / (cons_count / n)

                    rules.append({
                        "antecedent": set(antecedent),
                        "consequent": set(consequent),
                        "support": support,
                        "confidence": confidence,
                        "lift": lift,
                    })

        # 按提升度排序
        rules.sort(key=lambda r: r["lift"], reverse=True)
        return rules

    def _predict_from_rules(self, last_draw: Dict, rules: List[Dict],
                             key: str, pool_size: int) -> Dict[str, float]:
        """基于关联规则预测"""
        last_items = set(last_draw.get(key, []))
        scores = defaultdict(float)

        for rule in rules:
            # 检查前提是否匹配
            if rule["antecedent"].issubset(last_items):
                for item in rule["consequent"]:
                    scores[item] += rule["confidence"] * rule["lift"]

        return dict(scores)

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        n = len(data)
        min_support = 0.05

        # 前区关联规则
        freq_1_f, freq_2_f, freq_3_f, trans_f = self._get_itemsets(data, "front_balls", min_support)
        all_freq_f = {**freq_1_f, **freq_2_f, **freq_3_f}
        rules_f = self._generate_rules(all_freq_f, trans_f, n)

        # 后区关联规则
        freq_1_b, freq_2_b, freq_3_b, trans_b = self._get_itemsets(data, "back_balls", min_support * 2)
        all_freq_b = {**freq_1_b, **freq_2_b}
        rules_b = self._generate_rules(all_freq_b, trans_b, n)

        # 跨区规则（前区→后区）
        cross_rules = []
        for draw in data:
            fronts = set(draw.get("front_balls", []))
            backs = set(draw.get("back_balls", []))
            for f in fronts:
                for b in backs:
                    count = sum(1 for d in data
                               if f in d.get("front_balls", [])
                               and b in d.get("back_balls", []))
                    f_count = sum(1 for d in data if f in d.get("front_balls", []))
                    if f_count > 0 and count / f_count >= 0.2:
                        cross_rules.append({
                            "antecedent": {f},
                            "consequent": {b},
                            "confidence": count / f_count,
                            "lift": count / f_count / (sum(1 for d in data if b in d.get("back_balls", [])) / max(n, 1)),
                        })

        last_draw = data[0]

        # 4 组策略

        # 1. 高置信度规则
        high_conf = [r for r in rules_f if r["confidence"] > 0.3]
        scores1 = self._predict_from_rules(last_draw, high_conf, "front_balls", 35)
        front1 = [b for b, _ in sorted(scores1.items(), key=lambda x: x[1], reverse=True)[:5]]
        all_fronts = [format_ball(i) for i in range(1, 36)]
        for b in all_fronts:
            if len(front1) < 5 and b not in front1:
                front1.append(b)

        # 2. 高提升度规则
        high_lift = sorted(rules_f, key=lambda r: r["lift"], reverse=True)[:20]
        scores2 = self._predict_from_rules(last_draw, high_lift, "front_balls", 35)
        front2 = [b for b, _ in sorted(scores2.items(), key=lambda x: x[1], reverse=True)[:5]]
        for b in all_fronts:
            if len(front2) < 5 and b not in front2:
                front2.append(b)

        # 3. 频繁项集
        top_items = sorted(freq_2_f.items(), key=lambda x: x[1], reverse=True)
        front3 = list(set(item for itemset, _ in top_items[:10] for item in itemset))
        front3 = front3[:5]
        for b in all_fronts:
            if len(front3) < 5 and b not in front3:
                front3.append(b)

        # 4. 跨区规则
        cross_scores = defaultdict(float)
        for f in last_draw.get("front_balls", []):
            for rule in cross_rules:
                if f in rule["antecedent"]:
                    for b in rule["consequent"]:
                        cross_scores[b] += rule["confidence"]
        backs = [b for b, _ in sorted(cross_scores.items(), key=lambda x: x[1], reverse=True)[:2]]
        all_backs = [format_ball(i) for i in range(1, 13)]
        for b in all_backs:
            if len(backs) < 2 and b not in backs:
                backs.append(b)

        front4 = front3[:5]  # 复用频繁项集结果
        for b in all_fronts:
            if len(front4) < 5 and b not in front4:
                front4.append(b)

        # 后区
        back_scores = defaultdict(float)
        for rule in rules_b:
            if rule["antecedent"].issubset(set(last_draw.get("back_balls", []))):
                for item in rule["consequent"]:
                    back_scores[item] += rule["confidence"]
        back1 = [b for b, _ in sorted(back_scores.items(), key=lambda x: x[1], reverse=True)[:2]]
        for b in all_backs:
            if len(back1) < 2 and b not in back1:
                back1.append(b)
        back2 = list(back1)
        back3 = list(back1)

        from .base import get_interval_distribution, compute_sum

        d1 = f"高置信度规则(conf>0.3)；{len(high_conf)}条规则命中；和值{compute_sum(front1)}"
        d2 = f"高提升度规则(Lift Top20)；{len(high_lift)}条规则；和值{compute_sum(front2)}"
        d3 = f"频繁2-项集Top10；support={top_items[0][1]:.3f}；和值{compute_sum(front3)}"
        d4 = f"跨区规则(前→后)；{len(cross_rules)}条规则；后区推荐{backs}"

        strategies = [
            ("高置信度关联规则", front1, back1, d1),
            ("高提升度关联规则", front2, back2, d2),
            ("频繁项集挖掘", front3, back3, d3),
            ("跨区关联规则", front4, backs, d4),
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