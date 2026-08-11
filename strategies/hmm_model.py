# -*- coding: utf-8 -*-
"""
⑨ 隐马尔可夫模型 HMM 预测模型
通过隐状态建模发现号码的隐含模式
"""

import math
import random
from collections import defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    get_interval, compute_sum, validate_prediction_group
)


class HMMStrategy(BaseStrategy):
    """隐马尔可夫模型 HMM 预测模型"""

    MODEL_ID = "hidden-markov-model"
    MODEL_NAME = "隐马尔可夫HMM"
    MODEL_TYPE = "deep"

    def _compute_observation(self, data: List[Dict], key: str = "front_balls",
                              pool_size: int = 35) -> List[List[int]]:
        """计算观测序列"""
        obs = []
        for draw in data:
            balls = draw.get(key, [])
            vec = [1 if format_ball(i) in balls else 0 for i in range(1, pool_size + 1)]
            obs.append(vec)
        return obs

    def _initialize_hmm(self, n_states: int, n_obs: int) -> Dict:
        """初始化 HMM 参数"""
        # 状态转移矩阵 A
        A = [[random.random() for _ in range(n_states)] for _ in range(n_states)]
        for i in range(n_states):
            total = sum(A[i])
            A[i] = [v / total for v in A[i]]

        # 发射矩阵 B（高斯分布简化版）
        B = [[random.random() for _ in range(n_obs)] for _ in range(n_states)]
        for i in range(n_states):
            total = sum(B[i])
            B[i] = [v / total for v in B[i]]

        # 初始状态分布 π
        pi = [random.random() for _ in range(n_states)]
        total = sum(pi)
        pi = [v / total for v in pi]

        return {"A": A, "B": B, "pi": pi}

    def _forward(self, obs_seq: List[int], hmm: Dict) -> List[List[float]]:
        """Forward 算法计算前向概率"""
        n_states = len(hmm["A"])
        T = len(obs_seq)
        alpha = [[0.0] * n_states for _ in range(T)]

        # 初始化
        for i in range(n_states):
            alpha[0][i] = hmm["pi"][i] * hmm["B"][i][obs_seq[0]]

        # 递推
        for t in range(1, T):
            for j in range(n_states):
                total = 0.0
                for i in range(n_states):
                    total += alpha[t-1][i] * hmm["A"][i][j]
                alpha[t][j] = total * hmm["B"][j][obs_seq[t]]

        return alpha

    def _viterbi(self, obs_seq: List[int], hmm: Dict) -> Tuple[List[int], float]:
        """Viterbi 解码"""
        n_states = len(hmm["A"])
        T = len(obs_seq)

        if T == 0:
            return [], 0.0

        delta = [[0.0] * n_states for _ in range(T)]
        psi = [[0] * n_states for _ in range(T)]

        # 初始化
        for i in range(n_states):
            delta[0][i] = math.log(hmm["pi"][i] + 1e-10) + math.log(hmm["B"][i][obs_seq[0]] + 1e-10)

        # 递推
        for t in range(1, T):
            for j in range(n_states):
                max_val = float('-inf')
                max_idx = 0
                for i in range(n_states):
                    val = delta[t-1][i] + math.log(hmm["A"][i][j] + 1e-10)
                    if val > max_val:
                        max_val = val
                        max_idx = i
                delta[t][j] = max_val + math.log(hmm["B"][j][obs_seq[t]] + 1e-10)
                psi[t][j] = max_idx

        # 回溯
        last_state = max(range(n_states), key=lambda i: delta[T-1][i])
        path = [last_state]
        for t in range(T-1, 0, -1):
            path.insert(0, psi[t][path[0]])

        return path, delta[T-1][last_state]

    def _train_em(self, obs_seq: List[int], n_states: int, n_obs: int,
                  max_iter: int = 50) -> Dict:
        """Baum-Welch EM 训练"""
        hmm = self._initialize_hmm(n_states, n_obs)
        T = len(obs_seq)

        if T == 0:
            return hmm

        for iteration in range(max_iter):
            # E-step: Forward-Backward
            alpha = self._forward(obs_seq, hmm)

            # 计算后验概率 γ_t(i) 和 ξ_t(i,j)
            # 简化版：直接用 Viterbi 路径
            path, _ = self._viterbi(obs_seq, hmm)

            # M-step: 更新参数
            # 更新 A
            A_new = [[0.0] * n_states for _ in range(n_states)]
            for t in range(T - 1):
                i = path[t]
                j = path[t + 1]
                A_new[i][j] += 1.0

            for i in range(n_states):
                total = sum(A_new[i])
                if total > 0:
                    A_new[i] = [v / total for v in A_new[i]]
                else:
                    A_new[i] = [1.0 / n_states] * n_states

            # 更新 B
            B_new = [[0.0] * n_obs for _ in range(n_states)]
            for t in range(T):
                i = path[t]
                B_new[i][obs_seq[t]] += 1.0

            for i in range(n_states):
                total = sum(B_new[i])
                if total > 0:
                    B_new[i] = [v / total for v in B_new[i]]
                else:
                    B_new[i] = [1.0 / n_obs] * n_obs

            # 更新 π
            pi_new = [0.0] * n_states
            if path:
                pi_new[path[0]] = 1.0

            hmm = {"A": A_new, "B": B_new, "pi": pi_new}

        return hmm

    def _predict_next(self, hmm: Dict, current_state: int,
                       obs_seq: List[int]) -> List[int]:
        """预测下一期观测"""
        # 预测下一状态
        next_state_probs = hmm["A"][current_state]
        next_state = max(range(len(next_state_probs)), key=lambda i: next_state_probs[i])

        # 从发射分布中采样
        emission = hmm["B"][next_state]
        return emission

    def _predict_balls(self, emissions: List[float], pool_size: int,
                        count: int) -> List[str]:
        """从发射概率中选号码"""
        sorted_balls = sorted(
            [(format_ball(i), emissions[i] if i < len(emissions) else 0.0)
             for i in range(1, pool_size + 1)],
            key=lambda x: x[1], reverse=True
        )
        selected = [b for b, _ in sorted_balls[:count]]
        all_balls = [format_ball(i) for i in range(1, pool_size + 1)]
        for b in all_balls:
            if len(selected) < count and b not in selected:
                selected.append(b)
        return selected

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        # 前区观测序列
        front_obs = self._compute_observation(data, "front_balls", 35)
        # 简化为每个观测一个值（频率最高的号码）
        front_seq = []
        for obs in front_obs:
            active = [i for i, v in enumerate(obs) if v > 0]
            front_seq.append(active[0] if active else 0)

        # 后区观测序列
        back_obs = self._compute_observation(data, "back_balls", 12)
        back_seq = []
        for obs in back_obs:
            active = [i for i, v in enumerate(obs) if v > 0]
            back_seq.append(active[0] if active else 0)

        # 4 组策略：不同隐状态数
        configs = [
            dict(n_states=3, label="3态热号"),
            dict(n_states=4, label="4态平衡"),
            dict(n_states=5, label="5态全面"),
            dict(n_states=3, label="自适应窗口", use_window=True),
        ]

        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        predictions = []
        config_idx = 0
        for config in configs:
            config_idx += 1
            random.seed(42 + config_idx)

            n_states = config["n_states"]
            seq = front_seq
            if config.get("use_window"):
                # 使用最近一半数据
                window = max(len(seq) // 2, 10)
                seq = seq[-window:]
            else:
                seq = front_seq

            if len(seq) < 3:
                continue

            # 训练 HMM
            hmm = self._train_em(seq, n_states, 35, max_iter=30)

            # 解码当前状态
            path, _ = self._viterbi(seq, hmm)
            current_state = path[-1] if path else 0

            # 预测下一期
            emissions = self._predict_next(hmm, current_state, seq)

            # 选号码
            front = self._predict_balls(emissions, 35, 5)
            front = sort_balls(front)

            # 后区
            back_seq_use = back_seq
            if config.get("use_window"):
                back_seq_use = back_seq[-max(len(back_seq)//2, 10):]
            back_hmm = self._train_em(back_seq_use, 3, 12, max_iter=20)
            back_path, _ = self._viterbi(back_seq_use, back_hmm)
            back_state = back_path[-1] if back_path else 0
            back_emissions = self._predict_next(back_hmm, back_state, back_seq_use)
            backs = self._predict_balls(back_emissions, 12, 2)
            backs = sort_balls(backs)

            # 检查 state 分布描述
            state_desc = f"状态{current_state+1}"
            desc = f"{config['label']}({n_states}隐状态)；当前{state_desc}；P(Top)={emissions[0]:.4f}；和值{compute_sum(front)}"

            pred = {
                "group_id": config_idx,
                "strategy": f"HMM-{config['label']}",
                "front_balls": front,
                "back_balls": backs,
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)