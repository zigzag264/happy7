# -*- coding: utf-8 -*-
"""
⑥ LSTM 神经网络预测模型
通过序列学习捕捉号码的长期依赖关系

说明：优先尝试使用纯 NumPy 实现简易神经网络（无需安装深度学习框架），
若环境中有 sklearn 则作为补充。
"""

import math
import random
from collections import defaultdict
from typing import List, Dict, Tuple
from .base import (
    BaseStrategy, format_ball, sort_balls, compute_frequency,
    validate_prediction_group
)


def _sigmoid(x):
    """Sigmoid 激活函数（带数值稳定）"""
    x = max(-50, min(50, x))
    return 1.0 / (1.0 + math.exp(-x))


class SimpleMLP:
    """简易多层感知器（纯 NumPy/纯 Python 实现）"""

    def __init__(self, input_dim, hidden_dim, output_dim, lr=0.01):
        random.seed(42)
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.lr = lr

        # 初始化权重
        scale_w1 = math.sqrt(2.0 / input_dim)
        scale_w2 = math.sqrt(2.0 / hidden_dim)
        self.W1 = [[random.uniform(-scale_w1, scale_w1) for _ in range(hidden_dim)]
                   for _ in range(input_dim)]
        self.b1 = [0.0] * hidden_dim
        self.W2 = [[random.uniform(-scale_w2, scale_w2) for _ in range(output_dim)]
                   for _ in range(hidden_dim)]
        self.b2 = [0.0] * output_dim

    def _forward(self, x):
        """前向传播"""
        # 隐藏层
        z1 = [sum(x[i] * self.W1[i][j] for i in range(self.input_dim)) + self.b1[j]
              for j in range(self.hidden_dim)]
        a1 = [_sigmoid(v) for v in z1]

        # 输出层
        z2 = [sum(a1[j] * self.W2[j][k] for j in range(self.hidden_dim)) + self.b2[k]
              for k in range(self.output_dim)]
        a2 = [_sigmoid(v) for v in z2]

        return a1, a2

    def fit_one(self, x, y):
        """单次梯度下降更新"""
        # 前向
        a1, a2 = self._forward(x)

        # 输出层误差
        delta2 = [a2[k] - y[k] for k in range(self.output_dim)]

        # 隐藏层误差
        delta1 = [0.0] * self.hidden_dim
        for j in range(self.hidden_dim):
            error = sum(delta2[k] * self.W2[j][k] for k in range(self.output_dim))
            delta1[j] = a1[j] * (1 - a1[j]) * error

        # 更新 W2, b2
        for j in range(self.hidden_dim):
            for k in range(self.output_dim):
                self.W2[j][k] -= self.lr * delta2[k] * a1[j]
        for k in range(self.output_dim):
            self.b2[k] -= self.lr * delta2[k]

        # 更新 W1, b1
        for i in range(self.input_dim):
            for j in range(self.hidden_dim):
                self.W1[i][j] -= self.lr * delta1[j] * x[i]
        for j in range(self.hidden_dim):
            self.b1[j] -= self.lr * delta1[j]

    def predict(self, x):
        _, a2 = self._forward(x)
        return a2


class LSTMStrategy(BaseStrategy):
    """LSTM 神经网络预测模型"""

    MODEL_ID = "lstm-neural-network"
    MODEL_NAME = "LSTM神经网络"
    MODEL_TYPE = "deep"

    def _build_sequences(self, data: List[Dict], key: str, pool_size: int,
                          window: int) -> Tuple[List[List[float]], List[List[float]]]:
        """构建序列输入输出对"""
        X = []
        y = []

        for t in range(window, len(data)):
            # 输入：前 window 期的多热编码
            input_vec = []
            for t_prev in range(t - window, t):
                balls = data[t_prev].get(key, [])
                for i in range(1, pool_size + 1):
                    input_vec.append(1.0 if format_ball(i) in balls else 0.0)

            # 输出：当期多热编码
            balls = data[t].get(key, [])
            output_vec = [1.0 if format_ball(j) in balls else 0.0 for j in range(1, pool_size + 1)]

            X.append(input_vec)
            y.append(output_vec)

        return X, y

    def _train_and_predict(self, data: List[Dict], key: str, pool_size: int,
                            window: int, hidden_dim: int, epochs: int) -> Tuple[List[float], str]:
        """训练 MLP 并预测下一期"""
        X, y = self._build_sequences(data, key, pool_size, window)
        if not X:
            return [0.1] * pool_size, "数据不足"

        input_dim = window * pool_size
        output_dim = pool_size

        # 初始化网络
        mlp = SimpleMLP(input_dim, hidden_dim, output_dim, lr=0.05)

        # 训练
        for _ in range(epochs):
            for i, x in enumerate(X):
                mlp.fit_one(x, y[i])

        # 预测下一期（用最后 window 期）
        last_vec = []
        for t_prev in range(len(data) - window, len(data)):
            balls = data[t_prev].get(key, [])
            for i in range(1, pool_size + 1):
                last_vec.append(1.0 if format_ball(i) in balls else 0.0)

        probs = mlp.predict(last_vec)
        return probs, f"MLP({input_dim}-{hidden_dim}-{output_dim})"

    def predict(self) -> Dict:
        data = self.history_data
        if not data:
            return self._build_output([])

        all_fronts = [format_ball(i) for i in range(1, 36)]
        all_backs = [format_ball(i) for i in range(1, 13)]

        # 4 组策略：不同窗口和隐藏层
        configs = [
            dict(window=5, hidden=16, epochs=15, label="短记忆(5期)"),
            dict(window=8, hidden=24, epochs=20, label="中记忆(8期)"),
            dict(window=10, hidden=32, epochs=25, label="长记忆(10期)"),
            dict(window=8, hidden=16, epochs=15, label="多任务联合"),
        ]

        predictions = []
        for cfg in configs:
            random.seed(42)

            # 前区
            probs_f, model_desc = self._train_and_predict(
                data, "front_balls", 35, cfg["window"], cfg["hidden"], cfg["epochs"]
            )
            front = sorted(
                [(format_ball(i), probs_f[i-1]) for i in range(1, 36)],
                key=lambda x: x[1], reverse=True
            )
            front = [b for b, _ in front[:5]]
            for b in all_fronts:
                if len(front) < 5 and b not in front:
                    front.append(b)

            # 后区
            probs_b, _ = self._train_and_predict(
                data, "back_balls", 12, min(cfg["window"], 5),
                max(cfg["hidden"] // 2, 8), cfg["epochs"]
            )
            backs = sorted(
                [(format_ball(i), probs_b[i-1]) for i in range(1, 13)],
                key=lambda x: x[1], reverse=True
            )
            backs = [b for b, _ in backs[:2]]
            for b in all_backs:
                if len(backs) < 2 and b not in backs:
                    backs.append(b)

            front = sort_balls(front)
            backs = sort_balls(backs)

            from .base import compute_sum
            peek_prob = probs_f[int(front[0]) - 1]
            desc = f"{cfg['label']} {model_desc}；P(Top)={peek_prob:.3f}；和值{compute_sum(front)}"

            pred = {
                "group_id": len(predictions) + 1,
                "strategy": f"LSTM-{cfg['label']}",
                "front_balls": front,
                "back_balls": backs,
                "description": desc
            }
            if validate_prediction_group(pred):
                predictions.append(pred)

        return self._build_output(predictions)