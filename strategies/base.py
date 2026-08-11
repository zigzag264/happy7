# -*- coding: utf-8 -*-
"""
大乐透预测策略基类与通用工具函数
"""

import json
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from collections import Counter

# ==================== 通用工具函数 ====================

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOTTERY_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "lottery_history.json")
AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")


def load_history() -> Dict:
    """加载历史开奖数据"""
    with open(LOTTERY_HISTORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_next_draw_info(history: Dict) -> Tuple[str, str, str]:
    """从历史数据中提取下期信息"""
    next_draw = history.get("next_draw", {})
    target_period = next_draw.get("next_period", "")
    target_date = next_draw.get("next_date_display", "")
    prediction_date = next_draw.get("next_date", "")
    return target_period, target_date, prediction_date


def get_recent_draws(history: Dict, n: int = 30) -> List[Dict]:
    """获取最近 N 期开奖数据"""
    return history.get("data", [])[:n]


def format_ball(n: int) -> str:
    """格式化号码为两位字符串"""
    return f"{n:02d}"


def compute_frequency(data: List[Dict], pool_size: int = 35, key: str = "front_balls") -> Dict[str, int]:
    """计算号码频率"""
    counter = Counter()
    for draw in data:
        for ball in draw.get(key, []):
            counter[ball] += 1
    result = {}
    for i in range(1, pool_size + 1):
        b = format_ball(i)
        result[b] = counter.get(b, 0)
    return result


def compute_missing(data: List[Dict], pool_size: int = 35, key: str = "front_balls") -> Dict[str, int]:
    """计算每个号码的遗漏期数（距离上次出现的期数）"""
    missing = {}
    for i in range(1, pool_size + 1):
        b = format_ball(i)
        missing[b] = len(data)  # 默认全部遗漏
        for idx, draw in enumerate(data):
            if b in draw.get(key, []):
                missing[b] = idx
                break
    return missing


def compute_trend(freq_5: Dict[str, int], freq_30: Dict[str, int], pool_size: int = 35) -> Dict[str, float]:
    """计算趋势分数：(5期频率/5 - 30期频率/30) × 100"""
    trend = {}
    for i in range(1, pool_size + 1):
        b = format_ball(i)
        rate_5 = freq_5.get(b, 0) / 5.0
        rate_30 = freq_30.get(b, 0) / 30.0
        trend[b] = round((rate_5 - rate_30) * 100, 2)
    return trend


def get_interval(ball: str) -> int:
    """获取号码所在区间: 0=01-12, 1=13-24, 2=25-35"""
    n = int(ball)
    if n <= 12:
        return 0
    elif n <= 24:
        return 1
    else:
        return 2


def get_interval_distribution(fronts: List[str]) -> List[int]:
    """计算前区号码的区间分布 [count1, count2, count3]"""
    dist = [0, 0, 0]
    for b in fronts:
        dist[get_interval(b)] += 1
    return dist


def compute_parity(fronts: List[str]) -> str:
    """计算奇偶比，如 '3:2'"""
    odd = sum(1 for b in fronts if int(b) % 2 == 1)
    even = 5 - odd
    return f"{odd}:{even}"


def compute_sum(fronts: List[str]) -> int:
    """计算前区和值"""
    return sum(int(b) for b in fronts)


def sort_balls(balls: List[str]) -> List[str]:
    """号码排序"""
    return sorted(balls, key=int)


def pick_top_by_prob(probs: Dict[str, float], count: int) -> List[str]:
    """按概率从高到低选取 count 个号码"""
    sorted_items = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    return [item[0] for item in sorted_items[:count]]


def pick_top_by_score(scores: Dict[str, float], count: int) -> List[str]:
    """按分数从高到低选取 count 个号码"""
    return pick_top_by_prob(scores, count)


def validate_prediction_group(group: Dict) -> bool:
    """验证单组预测格式"""
    try:
        fronts = group.get("front_balls", [])
        backs = group.get("back_balls", [])

        if len(fronts) != 5:
            return False
        if len(backs) != 2:
            return False
        if fronts != sorted(fronts, key=int):
            return False
        if backs != sorted(backs, key=int):
            return False
        if len(set(fronts)) != 5:
            return False
        if len(set(backs)) != 2:
            return False

        for b in fronts:
            if not (1 <= int(b) <= 35):
                return False
        for b in backs:
            if not (1 <= int(b) <= 12):
                return False

        return True
    except Exception:
        return False


# ==================== 基类 ====================

class BaseStrategy(ABC):
    """所有策略模型的基类"""

    MODEL_ID: str = ""
    MODEL_NAME: str = ""
    MODEL_TYPE: str = "statistical"  # llm, statistical, ml, deep

    def __init__(self, history_data: List[Dict], target_period: str,
                 target_date: str, prediction_date: str):
        self.history_data = history_data
        self.target_period = target_period
        self.target_date = target_date
        self.prediction_date = prediction_date

    @abstractmethod
    def predict(self) -> Dict:
        """
        生成预测，返回格式：
        {
            "prediction_date": str,
            "target_period": str,
            "model_id": str,
            "model_name": str,
            "model_type": str,
            "predictions": [
                {
                    "group_id": 1,
                    "strategy": str,
                    "front_balls": List[str],
                    "back_balls": List[str],
                    "description": str
                }
            ]
        }
        """
        pass

    def _build_output(self, predictions: List[Dict]) -> Dict:
        """构建标准输出格式"""
        return {
            "prediction_date": self.prediction_date,
            "target_period": self.target_period,
            "model_id": self.MODEL_ID,
            "model_name": self.MODEL_NAME,
            "model_type": self.MODEL_TYPE,
            "predictions": predictions
        }

    def _make_prediction(self, strategy: str, front_balls: List[str],
                         back_balls: List[str], description: str) -> Dict:
        """构建单组预测"""
        return {
            "group_id": 1,
            "strategy": strategy,
            "front_balls": sort_balls(front_balls),
            "back_balls": sort_balls(back_balls),
            "description": description
        }