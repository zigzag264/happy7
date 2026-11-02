# -*- coding: utf-8 -*-
"""
策略裁剪模块 — 每个模型只保留历史累计命中最高的 N 种策略

排名依据 predictions_history.json:
  累计命中球数 > 后区命中数 > 前区命中数 > 出场期数 > 原始组序

用法:
    python -m strategies.selection              # 裁剪当前预测和历史归档
    python -m strategies.selection --dry-run    # 只打印排名,不修改文件
    python -m strategies.selection --top 3      # 指定每个模型保留的策略数
"""

import os
import sys
import json
import time
import argparse
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")
PREDICTIONS_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "predictions_history.json")
ARCHIVE_DIR = os.path.join(SCRIPT_DIR, "data", "archive")

DEFAULT_TOP_N = 3


def load_predictions_history(path=PREDICTIONS_HISTORY_FILE):
    """加载命中历史记录列表,文件缺失或损坏时返回空列表"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("predictions_history", [])
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"  ⚠️ 无法读取命中历史: {e}")
        return []


def compute_strategy_stats(records):
    """按 (model_id, strategy) 汇总历史命中数据"""
    stats = {}
    for record in records:
        for model in record.get("models", []):
            model_id = model.get("model_id")
            if not model_id:
                continue
            for group in model.get("predictions", []):
                strategy = group.get("strategy") or "—"
                key = (model_id, strategy)
                entry = stats.get(key)
                if entry is None:
                    entry = stats[key] = {
                        "model_id": model_id,
                        "model_name": model.get("model_name", model_id),
                        "strategy": strategy,
                        "total_hits": 0,
                        "front_hits": 0,
                        "back_hits": 0,
                        "games": 0,
                        "order": 0,
                    }
                hit = group.get("hit_result") or {}
                entry["total_hits"] += hit.get("total_hits", 0)
                entry["front_hits"] += hit.get("front_hit_count", 0)
                entry["back_hits"] += hit.get("back_hit_count", 0)
                entry["games"] += 1
                group_id = group.get("group_id")
                if isinstance(group_id, int) and group_id > 0:
                    entry["order"] = (
                        min(entry["order"], group_id) if entry["order"] else group_id
                    )
    return stats


def _sort_key(entry):
    return (
        -entry["total_hits"],
        -entry["back_hits"],
        -entry["front_hits"],
        -entry["games"],
        entry["order"],
        entry["strategy"],
    )


def _stats_by_model(records):
    stats = compute_strategy_stats(records)
    by_model = defaultdict(list)
    for entry in stats.values():
        by_model[entry["model_id"]].append(entry)
    for entries in by_model.values():
        entries.sort(key=_sort_key)
    return by_model


def select_top_strategies(records, top_n=DEFAULT_TOP_N):
    """返回 {model_id: [策略名, ...]},按历史累计命中从高到低"""
    if top_n <= 0:
        return {}
    by_model = _stats_by_model(records)
    return {
        model_id: [entry["strategy"] for entry in entries[:top_n]]
        for model_id, entries in by_model.items()
    }


def rank_strategies(records):
    """返回按累计命中排序的全部策略统计（供邮件排行复用）"""
    entries = list(compute_strategy_stats(records).values())
    entries.sort(key=_sort_key)
    return entries


def describe_selection(selection, records):
    """生成便于人工核对的排名文本"""
    by_model = _stats_by_model(records)
    lines = []
    for model_id in sorted(by_model):
        entries = by_model[model_id]
        kept = set(selection.get(model_id, []))
        lines.append(f"{entries[0]['model_name']} ({model_id})")
        for index, entry in enumerate(entries, 1):
            mark = "✓" if entry["strategy"] in kept else "✗"
            lines.append(
                f"  {mark} {index}. {entry['strategy']:<14s} "
                f"命中 {entry['total_hits']:>3d} 球"
                f" (前 {entry['front_hits']}, 后 {entry['back_hits']}, "
                f"{entry['games']} 期)"
            )
    return "\n".join(lines)


def _filter_model(model, selection, top_n):
    """保留指定策略,按排名顺序重新编号 G-1..G-n"""
    groups = model.get("predictions", [])
    wanted = selection.get(model.get("model_id"))

    if wanted:
        by_name = {}
        for group in groups:
            by_name.setdefault(group.get("strategy") or "—", group)
        chosen = []
        for name in wanted:
            group = by_name.get(name)
            if group is not None and group not in chosen:
                chosen.append(group)
        # 历史选出的策略在当前输出中缺失时,用其余组补齐
        for group in groups:
            if len(chosen) >= top_n:
                break
            if group not in chosen:
                chosen.append(group)
    else:
        chosen = list(groups)

    if top_n > 0:
        chosen = chosen[:top_n]

    out = []
    for index, group in enumerate(chosen, 1):
        group = dict(group)
        group["group_id"] = index
        out.append(group)

    model = dict(model)
    model["predictions"] = out
    return model


def filter_predictions(predictions, selection, top_n=DEFAULT_TOP_N):
    """裁剪一份预测数据(不修改入参)"""
    filtered = dict(predictions)
    filtered["models"] = [
        _filter_model(model, selection, top_n)
        for model in predictions.get("models", [])
    ]
    return filtered


def _prune_history_record(record, selection, top_n):
    record = dict(record)
    pruned_models = []
    for model in record.get("models", []):
        model = _filter_model(model, selection, top_n)
        predictions = model.get("predictions", [])
        if predictions:
            best = max(
                predictions,
                key=lambda g: (g.get("hit_result") or {}).get("total_hits", 0),
            )
            model["best_group"] = best.get("group_id")
            model["best_hit_count"] = (
                (best.get("hit_result") or {}).get("total_hits", 0)
            )
        pruned_models.append(model)
    record["models"] = pruned_models
    return record


def prune_predictions_history(records, selection, top_n=DEFAULT_TOP_N):
    """裁剪历史归档,并按保留后的组重新计算 best_group / best_hit_count"""
    return [_prune_history_record(record, selection, top_n) for record in records]


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def _backup(path, top_n):
    if not os.path.exists(path):
        return
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    name, ext = os.path.splitext(os.path.basename(path))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        ARCHIVE_DIR, f"{name}_backup_top{top_n}_{stamp}{ext}"
    )
    with open(path, "r", encoding="utf-8") as src:
        data = json.load(src)
    _dump(backup_path, data)
    print(f"  ✓ 已备份: {os.path.basename(backup_path)}")


def apply_top_strategies(top_n=DEFAULT_TOP_N, dry_run=False, backup=True):
    """裁剪 ai_predictions.json 与 predictions_history.json"""
    records = load_predictions_history()
    if not records:
        print("  ⚠️ 命中历史为空,无法排名,未做裁剪")
        return None

    selection = select_top_strategies(records, top_n)
    print(describe_selection(selection, records))

    if dry_run:
        print("\n(dry-run,未修改文件)")
        return selection

    if os.path.exists(AI_PREDICTIONS_FILE):
        if backup:
            _backup(AI_PREDICTIONS_FILE, top_n)
        with open(AI_PREDICTIONS_FILE, "r", encoding="utf-8") as f:
            predictions = json.load(f)
        filtered = filter_predictions(predictions, selection, top_n)
        _dump(AI_PREDICTIONS_FILE, filtered)
        print(f"\n  ✓ 已裁剪当前预测: {os.path.basename(AI_PREDICTIONS_FILE)}")

    if os.path.exists(PREDICTIONS_HISTORY_FILE):
        if backup:
            _backup(PREDICTIONS_HISTORY_FILE, top_n)
        with open(PREDICTIONS_HISTORY_FILE, "r", encoding="utf-8") as f:
            history_data = json.load(f)
        history_data["predictions_history"] = prune_predictions_history(
            records, selection, top_n
        )
        _dump(PREDICTIONS_HISTORY_FILE, history_data)
        print(f"  ✓ 已裁剪历史归档: {len(records)} 期 "
              f"({os.path.basename(PREDICTIONS_HISTORY_FILE)})")

    print(f"\n✅ 每个模型已只保留历史命中最高的 {top_n} 种策略")
    return selection


def main():
    parser = argparse.ArgumentParser(description="按历史命中裁剪模型策略")
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP_N,
        help=f"每个模型保留的策略数(默认 {DEFAULT_TOP_N})",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印排名,不修改文件")
    parser.add_argument("--no-backup", action="store_true", help="裁剪前不备份")
    args = parser.parse_args()
    apply_top_strategies(args.top, args.dry_run, backup=not args.no_backup)


if __name__ == "__main__":
    main()
