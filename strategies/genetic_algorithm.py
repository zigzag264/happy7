# -*- coding: utf-8 -*-
"""
⑧ 遗传算法优化预测模型
通过进化计算搜索最优号码组合
"""

import random
from collections import Counter, defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    compute_missing, get_interval, compute_sum, validate_prediction_group
)


class GeneticAlgorithmStrategy(BaseStrategy):
    """遗传算法优化预测模型"""

    MODEL_ID = "genetic-algorithm"
    MODEL_NAME = "遗传算法"
    MODEL_TYPE = "ml"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.front_freq = compute_frequency(self.history_data, 35, "front_balls")
        self.back_freq = compute_frequency(self.history_data, 12, "back_balls")
        self.front_missing = compute_missing(self.history_data, 35, "front_balls")
        self.back_missing = compute_missing(self.history_data, 12, "back_balls")

    def _random_individual(self) -> Tuple[List[str], List[str]]:
        """生成随机个体"""
        fronts = random.sample([format_ball(i) for i in range(1, 36)], 5)
        backs = random.sample([format_ball(i) for i in range(1, 13)], 2)
        return sort_balls(fronts), sort_balls(backs)

    def _fitness(self, fronts: List[str], backs: List[str],
                  w_freq: float, w_missing: float, w_dist: float,
                  w_trend: float) -> float:
        """计算适应度"""
        score = 0.0
        n = len(self.history_data)

        # 频率得分
        for b in fronts:
            score += w_freq * self.front_freq.get(b, 0) / max(n, 1)
        for b in backs:
            score += w_freq * self.back_freq.get(b, 0) / max(n, 1)

        # 遗漏得分（冷号补偿）
        max_missing = max(self.front_missing.values()) if self.front_missing else 1
        for b in fronts:
            miss = self.front_missing.get(b, 0)
            score += w_missing * miss / max(max_missing, 1)

        # 分布得分
        odd = sum(1 for b in fronts if int(b) % 2 == 1)
        if odd in [2, 3]:
            score += w_dist * 0.3

        s = compute_sum(fronts)
        if 80 <= s <= 120:
            score += w_dist * 0.3
        elif 70 <= s <= 130:
            score += w_dist * 0.15

        # 区间分布
        intervals = [get_interval(b) for b in fronts]
        interval_count = Counter(intervals)
        if len(interval_count) >= 2:
            score += w_dist * 0.2

        # 趋势得分
        for b in fronts:
            freq_5 = compute_frequency(self.history_data[:5], 35, "front_balls").get(b, 0)
            freq_30 = self.front_freq.get(b, 0)
            trend = (freq_5 / 5.0 - freq_30 / max(n, 1)) * 100
            if trend > 0:
                score += w_trend * trend / 100

        return score

    def _crossover(self, parent1: Tuple[List[str], List[str]],
                    parent2: Tuple[List[str], List[str]]) -> Tuple[Tuple[List[str], List[str]], Tuple[List[str], List[str]]]:
        """PMX 交叉"""
        f1, b1 = parent1
        f2, b2 = parent2

        # 前区交叉
        split = random.randint(1, 4)
        child1_f = f1[:split] + [b for b in f2[split:] if b not in f1[:split]]
        child2_f = f2[:split] + [b for b in f1[split:] if b not in f2[:split]]

        # 补全
        all_fronts = [format_ball(i) for i in range(1, 36)]
        for b in all_fronts:
            if len(child1_f) < 5 and b not in child1_f:
                child1_f.append(b)
            if len(child2_f) < 5 and b not in child2_f:
                child2_f.append(b)

        # 后区交叉
        child1_b = b1[:1] + [b for b in b2[1:] if b not in b1[:1]]
        child2_b = b2[:1] + [b for b in b1[1:] if b not in b2[:1]]
        all_backs = [format_ball(i) for i in range(1, 13)]
        for b in all_backs:
            if len(child1_b) < 2 and b not in child1_b:
                child1_b.append(b)
            if len(child2_b) < 2 and b not in child2_b:
                child2_b.append(b)

        return (sort_balls(child1_f[:5]), sort_balls(child1_b[:2])), \
               (sort_balls(child2_f[:5]), sort_balls(child2_b[:2]))

    def _mutate(self, individual: Tuple[List[str], List[str]],
                 mutation_rate: float = 0.1) -> Tuple[List[str], List[str]]:
        """变异"""
        fronts, backs = list(individual[0]), list(individual[1])
        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        # 前区变异
        for i in range(5):
            if random.random() < mutation_rate:
                candidates = [b for b in all_fronts if b not in fronts]
                if candidates:
                    fronts[i] = random.choice(candidates)

        # 后区变异
        for i in range(2):
            if random.random() < mutation_rate:
                candidates = [b for b in all_backs if b not in backs]
                if candidates:
                    backs[i] = random.choice(candidates)

        return sort_balls(fronts), sort_balls(backs)

    def _evolve(self, pop_size: int, generations: int, mutation_rate: float,
                 w_freq: float, w_missing: float, w_dist: float,
                 w_trend: float) -> Tuple[List[str], List[str]]:
        """进化主循环"""
        # 初始化种群
        population = [self._random_individual() for _ in range(pop_size)]

        for gen in range(generations):
            # 计算适应度
            fitnesses = [self._fitness(f, b, w_freq, w_missing, w_dist, w_trend)
                        for f, b in population]

            # 选择（锦标赛）
            new_population = []
            for _ in range(pop_size // 2):
                # 锦标赛选择
                idx1 = random.randint(0, pop_size - 1)
                idx2 = random.randint(0, pop_size - 1)
                if fitnesses[idx1] > fitnesses[idx2]:
                    parent1 = population[idx1]
                else:
                    parent1 = population[idx2]

                idx3 = random.randint(0, pop_size - 1)
                idx4 = random.randint(0, pop_size - 1)
                if fitnesses[idx3] > fitnesses[idx4]:
                    parent2 = population[idx3]
                else:
                    parent2 = population[idx4]

                # 交叉
                child1, child2 = self._crossover(parent1, parent2)

                # 变异
                child1 = self._mutate(child1, mutation_rate)
                child2 = self._mutate(child2, mutation_rate)

                new_population.append(child1)
                new_population.append(child2)

            # 精英保留
            best_idx = max(range(pop_size), key=lambda i: fitnesses[i])
            new_population[0] = population[best_idx]

            population = new_population

        # 返回最优个体
        best_fitness = -1
        best_individual = population[0]
        for f, b in population:
            fit = self._fitness(f, b, w_freq, w_missing, w_dist, w_trend)
            if fit > best_fitness:
                best_fitness = fit
                best_individual = (f, b)

        return best_individual

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        POP_SIZE = 50
        GENERATIONS = 80

        # 4 组策略，不同的适应度权重
        configs = [
            dict(w_freq=0.35, w_missing=0.15, w_dist=0.30, w_trend=0.20, label="均衡进化", mr=0.1),
            dict(w_freq=0.50, w_missing=0.10, w_dist=0.20, w_trend=0.20, label="热号倾斜", mr=0.08),
            dict(w_freq=0.10, w_missing=0.40, w_dist=0.25, w_trend=0.25, label="冷号探索", mr=0.15),
            dict(w_freq=0.25, w_missing=0.20, w_dist=0.40, w_trend=0.15, label="均衡分布优化", mr=0.1),
        ]

        predictions = []
        for config in configs:
            random.seed(42)
            fronts, backs = self._evolve(
                POP_SIZE, GENERATIONS, config["mr"],
                config["w_freq"], config["w_missing"],
                config["w_dist"], config["w_trend"]
            )

            from .base import get_interval_distribution
            desc = f"{config['label']}(种群{POP_SIZE}, {GENERATIONS}代)；freq={config['w_freq']}, missing={config['w_missing']}；和值{compute_sum(fronts)}"

            pred = {
                "group_id": len(predictions) + 1,
                "strategy": f"遗传算法-{config['label']}",
                "front_balls": sort_balls(fronts),
                "back_balls": sort_balls(backs),
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)