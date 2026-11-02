# -*- coding: utf-8 -*-
"""
重置后三名模型的历史归档(v2 上线前使用)

默认 dry-run，只统计将被删除的条目；确认后加 --apply 才写文件。
写入前会把 predictions_history.json / ai_predictions.json 备份到 data/archive/。

用法:
    python -m strategies.reset_bottom3_history
    python -m strategies.reset_bottom3_history --apply
    python -m strategies.reset_bottom3_history --models ensemble-ml,monte-carlo,apriori-rules --apply
"""

import os
import sys
import json
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

PREDICTIONS_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "predictions_history.json")
AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")
ARCHIVE_DIR = os.path.join(SCRIPT_DIR, "data", "archive")

DEFAULT_MODELS = ["ensemble-ml", "monte-carlo", "apriori-rules"]


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def _backup(path):
    if not os.path.exists(path):
        return
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    name, ext = os.path.splitext(os.path.basename(path))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(ARCHIVE_DIR, f"{name}_backup_before_reset_{stamp}{ext}")
    _dump(backup_path, _load(path))
    print(f"  ✓ 已备份: {os.path.basename(backup_path)}")


def reset_history(model_ids, apply=False, backup=True):
    model_ids = set(model_ids)
    history = _load(PREDICTIONS_HISTORY_FILE)
    records = history.get("predictions_history", [])

    removed_by_record = 0
    remaining_records = 0
    for record in records:
        models = record.get("models", [])
        kept = [m for m in models if m.get("model_id") not in model_ids]
        removed_by_record += len(models) - len(kept)
        if kept:
            remaining_records += 1

    predictions = None
    current_removed = 0
    if os.path.exists(AI_PREDICTIONS_FILE):
        predictions = _load(AI_PREDICTIONS_FILE)
        current_removed = sum(
            1 for m in predictions.get("models", [])
            if m.get("model_id") in model_ids
        )

    print("=" * 60)
    print("重置后三名模型历史归档")
    print("=" * 60)
    print(f"  目标 model_id: {', '.join(sorted(model_ids))}")
    print(f"  命中历史: {len(records)} 期, 将删除 {removed_by_record} 条模型记录")
    print(f"  当前预测: 将删除 {current_removed} 个模型")
    print(f"  剩余有模型记录的期数: {remaining_records}/{len(records)}")

    if not apply:
        print("\n(dry-run,未修改文件;确认后加 --apply)")
        return

    if backup:
        _backup(PREDICTIONS_HISTORY_FILE)
        if predictions is not None:
            _backup(AI_PREDICTIONS_FILE)

    for record in records:
        record["models"] = [
            m for m in record.get("models", [])
            if m.get("model_id") not in model_ids
        ]
    _dump(PREDICTIONS_HISTORY_FILE, history)
    print(f"  ✓ 已裁剪命中历史: {os.path.basename(PREDICTIONS_HISTORY_FILE)}")

    if predictions is not None:
        predictions["models"] = [
            m for m in predictions.get("models", [])
            if m.get("model_id") not in model_ids
        ]
        _dump(AI_PREDICTIONS_FILE, predictions)
        print(f"  ✓ 已裁剪当前预测: {os.path.basename(AI_PREDICTIONS_FILE)}")

    print("\n✅ 重置完成。下一步运行 python -m strategies.runner 生成 v2 预测。")


def main():
    parser = argparse.ArgumentParser(description="重置后三名模型的历史归档")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS),
                        help="逗号分隔的 model_id")
    parser.add_argument("--apply", action="store_true", help="实际写入(默认 dry-run)")
    parser.add_argument("--no-backup", action="store_true", help="不备份")
    args = parser.parse_args()

    model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    reset_history(model_ids, apply=args.apply, backup=not args.no_backup)


if __name__ == "__main__":
    main()
