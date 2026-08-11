# -*- coding: utf-8 -*-
"""
大乐透预测策略包
"""

from .base import (
    BaseStrategy,
    load_history,
    get_next_draw_info,
    get_recent_draws,
    compute_frequency,
    compute_missing,
    compute_trend,
    format_ball,
    get_interval,
    get_interval_distribution,
    compute_parity,
    compute_sum,
    sort_balls,
    pick_top_by_prob,
    pick_top_by_score,
    validate_prediction_group,
    LOTTERY_HISTORY_FILE,
    AI_PREDICTIONS_FILE,
)

from .markov_chain import MarkovChainStrategy
from .bayesian import BayesianStrategy
from .monte_carlo import MonteCarloStrategy
from .genetic_algorithm import GeneticAlgorithmStrategy
from .csp_model import CSPStrategy
from .apriori import AprioriStrategy
from .arima_model import ArimaStrategy
from .hmm_model import HMMStrategy
from .ensemble_ml import EnsembleMLStrategy
from .lstm_model import LSTMStrategy


def get_all_strategies(history_data, target_period, target_date, prediction_date):
    """获取所有策略实例列表"""
    return [
        MarkovChainStrategy(history_data, target_period, target_date, prediction_date),
        BayesianStrategy(history_data, target_period, target_date, prediction_date),
        ArimaStrategy(history_data, target_period, target_date, prediction_date),
        MonteCarloStrategy(history_data, target_period, target_date, prediction_date),
        EnsembleMLStrategy(history_data, target_period, target_date, prediction_date),
        LSTMStrategy(history_data, target_period, target_date, prediction_date),
        AprioriStrategy(history_data, target_period, target_date, prediction_date),
        GeneticAlgorithmStrategy(history_data, target_period, target_date, prediction_date),
        HMMStrategy(history_data, target_period, target_date, prediction_date),
        CSPStrategy(history_data, target_period, target_date, prediction_date),
    ]


__all__ = [
    "BaseStrategy",
    "MarkovChainStrategy",
    "BayesianStrategy",
    "MonteCarloStrategy",
    "GeneticAlgorithmStrategy",
    "CSPStrategy",
    "AprioriStrategy",
    "ArimaStrategy",
    "HMMStrategy",
    "EnsembleMLStrategy",
    "LSTMStrategy",
    "get_all_strategies",
    "load_history",
    "get_next_draw_info",
    "get_recent_draws",
    "validate_prediction_group",
]