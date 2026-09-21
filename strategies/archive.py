# -*- coding: utf-8 -*-
"""
预测归档模块 — 开奖后将上一期预测与开奖结果比对，追加到 predictions_history.json

由 strategies.runner 在生成新预测前调用，也可独立运行：
    python -m strategies.archive

幂等：目标期未开奖 / 已归档 / 文件缺失时安全跳过，不产生重复记录。
"""

import os
import sys
import json

# 允许从项目根目录导入（独立运行时）
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "lottery_history.json")
PREDICTIONS_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "predictions_history.json")


def calculate_hit_result(prediction_group, actual_result):
    """计算单组预测的命中情况（与既有记录格式一致）"""
    front_hits = [b for b in prediction_group["front_balls"] if b in actual_result["front_balls"]]
    back_hits = [b for b in prediction_group["back_balls"] if b in actual_result["back_balls"]]
    return {
        "front_hits": front_hits,
        "front_hit_count": len(front_hits),
        "back_hits": back_hits,
        "back_hit_count": len(back_hits),
        "total_hits": len(front_hits) + len(back_hits),
    }


def build_history_record(predictions, actual_result):
    """用开奖结果比对整份预测，生成一条命中历史记录。

    字段与 8 月重构前的旧记录保持一致：
    record: prediction_date / target_period / actual_result / models
    model:  model_id / model_name / predictions(含 hit_result) / best_group / best_hit_count
    """
    models = []
    for m in predictions.get("models", []):
        preds_with_hits = []
        for g in m.get("predictions", []):
            g2 = dict(g)
            g2["hit_result"] = calculate_hit_result(g, actual_result)
            preds_with_hits.append(g2)
        if not preds_with_hits:
            continue
        best = max(preds_with_hits, key=lambda p: p["hit_result"]["total_hits"])
        models.append({
            "model_id": m.get("model_id"),
            "model_name": m.get("model_name"),
            "predictions": preds_with_hits,
            "best_group": best.get("group_id"),
            "best_hit_count": best["hit_result"]["total_hits"],
        })
    return {
        "prediction_date": predictions.get("prediction_date", ""),
        "target_period": str(predictions.get("target_period", "")),
        "actual_result": actual_result,
        "models": models,
    }


def archive_prediction_if_drawn(predictions_file=AI_PREDICTIONS_FILE,
                                history_file=HISTORY_FILE,
                                out_file=PREDICTIONS_HISTORY_FILE):
    """若当前 ai_predictions 的目标期已开奖，则比对命中并归档。

    返回 True 表示写入了新记录；其余情况安全跳过返回 False。
    """
    try:
        with open(predictions_file, "r", encoding="utf-8") as f:
            predictions = json.load(f)
    except Exception as e:
        print(f"  ⚠️ 无法读取当前预测，跳过归档: {e}")
        return False

    target = str(predictions.get("target_period", "") or "")
    if not target:
        print("  ⚠️ 当前预测缺少 target_period，跳过归档")
        return False

    try:
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        print(f"  ⚠️ 无法读取开奖历史，跳过归档: {e}")
        return False

    actual = next((d for d in history.get("data", []) if str(d.get("period")) == target), None)
    if actual is None:
        print(f"  ℹ️ 第 {target} 期尚未开奖，无需归档")
        return False

    try:
        with open(out_file, "r", encoding="utf-8") as f:
            history_data = json.load(f)
    except Exception:
        history_data = {"predictions_history": []}
    history_data.setdefault("predictions_history", [])

    if any(str(r.get("target_period")) == target for r in history_data["predictions_history"]):
        print(f"  ℹ️ 第 {target} 期已在命中历史中，跳过归档")
        return False

    record = build_history_record(predictions, actual)
    history_data["predictions_history"].insert(0, record)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"  ✓ 已归档第 {target} 期命中结果（{len(record['models'])} 个模型）→ {os.path.basename(out_file)}")
    return True


if __name__ == "__main__":
    print("🗂️  检查上一期预测归档...")
    archive_prediction_if_drawn()
