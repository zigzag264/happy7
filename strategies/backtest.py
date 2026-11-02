# -*- coding: utf-8 -*-
"""
Walk-forward 回测 — 逐期截断历史数据,重跑模型并统计命中。

用法:
    python -m strategies.backtest
    python -m strategies.backtest --models rf,mc,apriori --periods 33 --seeds 3
    python -m strategies.backtest --models rf --periods 5 --seeds 1 --progress
    python -m strategies.backtest --json data/archive/backtest_v2.json

说明:
  - history_data 与线上一致,均为 newest-first,只包含目标期之前的数据。
  - 目标期默认取 predictions_history 最近 N 期,保证与线上归档同口径。
  - 复用 archive.calculate_hit_result 计算命中,避免口径不一致。
"""

import os
import sys
import json
import time
import random
import argparse
from collections import Counter
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from strategies.base import load_history
from strategies.archive import calculate_hit_result, PREDICTIONS_HISTORY_FILE
from strategies.ensemble_ml import EnsembleMLStrategy
from strategies.monte_carlo import MonteCarloStrategy
from strategies.apriori import AprioriStrategy

MODEL_ALIASES = {
    "rf": EnsembleMLStrategy,
    "ensemble-ml": EnsembleMLStrategy,
    "mc": MonteCarloStrategy,
    "monte-carlo": MonteCarloStrategy,
    "apriori": AprioriStrategy,
    "apriori-rules": AprioriStrategy,
}
DEFAULT_MODELS = ["rf", "mc", "apriori"]


def load_target_records(periods):
    """最近 N 期归档记录,按时间从旧到新返回"""
    with open(PREDICTIONS_HISTORY_FILE, "r", encoding="utf-8") as f:
        records = json.load(f).get("predictions_history", [])
    records = records[:periods]
    return list(reversed(records))


def _aggregate(records, seeds):
    """把逐注命中记录聚合成 模型/策略 指标"""
    strategies = {}
    for r in records:
        s = strategies.get(r["strategy"])
        if s is None:
            s = strategies[r["strategy"]] = {
                "games": 0, "total": 0, "front": 0, "back": 0,
                "best": 0, "hits": Counter(),
            }
        s["games"] += 1
        s["total"] += r["total"]
        s["front"] += r["front"]
        s["back"] += r["back"]
        s["best"] = max(s["best"], r["total"])
        s["hits"][r["total"]] += 1

    periods = sorted({str(r["period"]) for r in records}, key=int)
    recent_periods = set(periods[-10:])

    def _finish(games, total, front, back, best, hits, recent_total, recent_games):
        return {
            "games": games,
            "total": total,
            "total_per_seed": round(total / seeds, 2),
            "avg": round(total / games, 3) if games else 0,
            "front": front,
            "front_per_seed": round(front / seeds, 2),
            "back": back,
            "back_per_seed": round(back / seeds, 2),
            "best": best,
            "hit_distribution": {str(k): v for k, v in sorted(hits.items())},
            "recent10_avg": round(recent_total / recent_games, 3) if recent_games else 0,
        }

    strategy_out = {}
    for name, s in strategies.items():
        recent = [r for r in records
                  if r["strategy"] == name and str(r["period"]) in recent_periods]
        strategy_out[name] = _finish(
            s["games"], s["total"], s["front"], s["back"], s["best"], s["hits"],
            sum(r["total"] for r in recent), len(recent),
        )

    recent_records = [r for r in records if str(r["period"]) in recent_periods]
    all_hits = Counter()
    for s in strategies.values():
        all_hits.update(s["hits"])
    model_out = _finish(
        len(records),
        sum(r["total"] for r in records),
        sum(r["front"] for r in records),
        sum(r["back"] for r in records),
        max((r["total"] for r in records), default=0),
        all_hits,
        sum(r["total"] for r in recent_records), len(recent_records),
    )
    model_out["strategies"] = strategy_out
    return model_out


def run_backtest(model_keys, periods=33, window=30, seeds=3,
                 exclude_strategies=None, min_history=10, progress=False):
    history = load_history()
    draws = history.get("data", [])  # newest-first
    period_index = {str(d.get("period")): i for i, d in enumerate(draws)}
    period_draw = {str(d.get("period")): d for d in draws}

    targets = load_target_records(periods)
    exclude = set(exclude_strategies or [])
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "params": {
            "periods": periods, "window": window, "seeds": seeds,
            "models": model_keys, "exclude_strategies": sorted(exclude),
        },
        "targets": [str(r.get("target_period")) for r in targets],
        "models": {},
    }

    for model_key in model_keys:
        cls = MODEL_ALIASES[model_key]
        model_records = []
        model_start = time.time()

        for idx, rec in enumerate(targets, 1):
            period = str(rec.get("target_period") or "")
            target_idx = period_index.get(period)
            actual = rec.get("actual_result") or period_draw.get(period)
            if target_idx is None or not actual:
                if progress:
                    print(f"  ⚠️ 跳过 {period or '?'}: 缺少开奖数据")
                continue

            # 目标期之前的数据,保持 newest-first 与线上一致
            history_data = draws[target_idx + 1: target_idx + 1 + window]
            if len(history_data) < min_history:
                if progress:
                    print(f"  ⚠️ 跳过 {period}: 历史不足（{len(history_data)} 期）")
                continue

            target_date = actual.get("date", "")
            for seed_idx in range(seeds):
                random.seed(seed_idx)
                model = cls(history_data, period, target_date, target_date)
                model.seed_salt = seed_idx
                output = model.predict()
                for group in output.get("predictions", []):
                    strategy = group.get("strategy", "—")
                    if strategy in exclude:
                        continue
                    hit = calculate_hit_result(group, actual)
                    model_records.append({
                        "period": period,
                        "strategy": strategy,
                        "total": hit["total_hits"],
                        "front": hit["front_hit_count"],
                        "back": hit["back_hit_count"],
                    })

            if progress:
                print(f"  [{idx}/{len(targets)}] {period} 完成")

        model_out = _aggregate(model_records, seeds)
        model_out["model_name"] = getattr(cls, "MODEL_NAME", model_key)
        model_out["elapsed"] = round(time.time() - model_start, 1)
        report["models"][getattr(cls, "MODEL_ID", model_key)] = model_out

    return report


def print_report(report, baseline=None):
    print("=" * 78)
    print(f"回测: {report['params']['periods']} 期 | 窗口 {report['params']['window']} | "
          f"种子 {report['params']['seeds']}")
    print("=" * 78)

    for model_id, m in report["models"].items():
        print(f"\n{m['model_name']} ({model_id})  用时 {m['elapsed']}s")
        print(f"  {'策略':<20}{'注数':>6}{'总/种子':>9}{'均值':>8}{'前/种子':>9}{'后/种子':>9}{'近10':>8}")
        for name, s in m["strategies"].items():
            print(f"  {name:<20}{s['games']:>6}{s['total_per_seed']:>9.1f}"
                  f"{s['avg']:>8.2f}{s['front_per_seed']:>9.1f}"
                  f"{s['back_per_seed']:>9.1f}{s['recent10_avg']:>8.2f}")
        print(f"  {'模型合计':<20}{m['games']:>6}{m['total_per_seed']:>9.1f}"
              f"{m['avg']:>8.2f}{m['front_per_seed']:>9.1f}"
              f"{m['back_per_seed']:>9.1f}{m['recent10_avg']:>8.2f}")

    if baseline:
        print("\n" + "=" * 78)
        print("与基线对比（均值/注）")
        print("=" * 78)
        print(f"  {'模型':<16}{'旧版':>8}{'新版':>8}{'差值':>8}{'旧前/后':>14}{'新前/后':>14}")
        for model_id, m in report["models"].items():
            b = (baseline.get("models") or {}).get(model_id)
            if not b:
                continue
            print(f"  {m['model_name']:<16}{b['avg']:>8.2f}{m['avg']:>8.2f}"
                  f"{m['avg'] - b['avg']:>+8.2f}"
                  f"{b['front_per_seed']:>7.1f}/{b['back_per_seed']:<6.1f}"
                  f"{m['front_per_seed']:>7.1f}/{m['back_per_seed']:<6.1f}")


def main():
    parser = argparse.ArgumentParser(description="Walk-forward 回测")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS),
                        help="rf,mc,apriori 或逗号分隔的别名")
    parser.add_argument("--periods", type=int, default=33, help="回测期数(默认 33)")
    parser.add_argument("--window", type=int, default=30, help="每期输入的历史窗口(默认 30)")
    parser.add_argument("--seeds", type=int, default=3, help="每期随机种子数(默认 3)")
    parser.add_argument("--min-history", type=int, default=10, help="最少历史期数")
    parser.add_argument("--exclude-strategies", default="",
                        help="排除的策略名,逗号分隔")
    parser.add_argument("--json", help="将报告写入 JSON 文件")
    parser.add_argument("--baseline", help="旧版报告 JSON,用于对比")
    parser.add_argument("--progress", action="store_true", help="打印逐期进度")
    args = parser.parse_args()

    model_keys = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in model_keys if m not in MODEL_ALIASES]
    if unknown:
        parser.error(f"未知模型: {', '.join(unknown)}")

    exclude = [s.strip() for s in args.exclude_strategies.split(",") if s.strip()]
    report = run_backtest(
        model_keys, periods=args.periods, window=args.window, seeds=args.seeds,
        exclude_strategies=exclude, min_history=args.min_history,
        progress=args.progress,
    )

    baseline = None
    if args.baseline:
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline = json.load(f)
    print_report(report, baseline)

    if args.json:
        parent = os.path.dirname(os.path.abspath(args.json))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 报告已写入 {args.json}")


if __name__ == "__main__":
    main()
