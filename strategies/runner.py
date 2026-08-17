# -*- coding: utf-8 -*-
"""
大乐透策略模型运行入口
运行所有 10 个统计/机器学习模型，生成预测并保存

用法：
    python -m strategies.runner              # 运行所有模型
    python -m strategies.runner --models 1,2 # 只运行指定模型
    python -m strategies.runner --output f.json # 指定输出文件
"""

import os
import sys
import json
import argparse
import time

# 允许从项目根目录导入 strategies 包
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from strategies import get_all_strategies
from strategies.base import load_history, get_next_draw_info, get_recent_draws

AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")


def run_all_strategies(history, target_period, target_date, prediction_date,
                       models_to_run=None):
    """运行所有策略模型"""
    history_data = get_recent_draws(history, 30)

    all_strategies = get_all_strategies(
        history_data, target_period, target_date, prediction_date
    )

    if models_to_run:
        all_strategies = [s for s in all_strategies if s.MODEL_ID in models_to_run]

    results = []
    diagnostics = []

    print("\n" + "=" * 60)
    print("🧠 大乐透 10 种统计/ML 模型预测")
    print("=" * 60 + "\n")

    for strategy in all_strategies:
        model_name = strategy.MODEL_NAME
        start = time.time()
        try:
            output = strategy.predict()
            elapsed = time.time() - start

            if output and output.get("predictions"):
                results.append(output)
                n_pred = len(output["predictions"])
                print(f"  ✅ {model_name:<12s} 完成 | 耗时 {elapsed:.2f}s | {n_pred} 组预测")
                for pred in output["predictions"]:
                    if validate_output(pred):
                        pass
            else:
                print(f"  ⚠️  {model_name:<12s} 无有效预测")

            diagnostics.append({
                "name": model_name,
                "model_id": strategy.MODEL_ID,
                "model_type": strategy.MODEL_TYPE,
                "status": "✅ 成功" if output and output.get("predictions") else "❌ 失败",
                "elapsed": elapsed,
            })
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ {model_name:<12s} 出错: {e}")
            diagnostics.append({
                "name": model_name,
                "model_id": strategy.MODEL_ID,
                "model_type": strategy.MODEL_TYPE,
                "status": "❌ 失败",
                "elapsed": elapsed,
            })

    print("\n" + "=" * 60)
    print("📊 运行汇总")
    print("=" * 60)
    for d in diagnostics:
        print(f"  {d['status']} | {d['name']:<12s} | {d['elapsed']:.2f}s")
    print("=" * 60)
    print(f"  成功: {sum(1 for d in diagnostics if d['status'] == '✅ 成功')}/{len(diagnostics)}\n")

    return {
        "prediction_date": prediction_date,
        "target_period": target_period,
        "models": results,
    }


def validate_output(prediction):
    """验证单组预测"""
    try:
        fronts = prediction.get("front_balls", [])
        backs = prediction.get("back_balls", [])
        if len(fronts) != 5 or len(backs) != 2:
            return False
        if fronts != sorted(fronts, key=int):
            return False
        if backs != sorted(backs, key=int):
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


def save_predictions(output, output_file=None):
    """保存预测到文件"""
    target = output_file or AI_PREDICTIONS_FILE

    # 备份现有文件（保留漂亮格式方便人工查验）
    if os.path.exists(target):
        archive_dir = os.path.join(os.path.dirname(target), "archive")
        os.makedirs(archive_dir, exist_ok=True)
        backup_file = os.path.join(
            archive_dir,
            f"ai_predictions_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(target, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 已备份: {os.path.basename(backup_file)}")

    # 剥离模型层冗余字段（顶层已有 prediction_date/target_period）
    for model in output.get("models", []):
        model.pop("prediction_date", None)
        model.pop("target_period", None)

    # 保存新预测（紧凑格式，生产环境用）
    with open(target, 'w', encoding='utf-8') as f:
        json_str = json.dumps(output, ensure_ascii=False, separators=(',', ':'))
        f.write(json_str)

    print(f"\n💾 已保存 {len(output.get('models', []))} 个模型预测到 {os.path.basename(target)}（紧凑格式，{len(json_str)} bytes）\n")


def main():
    parser = argparse.ArgumentParser(description='大乐透策略模型运行器')
    parser.add_argument('--models', type=str, help='要运行的模型ID（逗号分隔）')
    parser.add_argument('--output', type=str, help='指定输出文件路径')
    parser.add_argument('--list', action='store_true', help='列出所有可用模型')
    args = parser.parse_args()

    # 列出模型
    if args.list:
        print("\n可用模型：")
        all_fronts = [[], []]
        for s in get_all_strategies([], "0", "date", "date"):
            print(f"  - {s.MODEL_ID}: {s.MODEL_NAME} ({s.MODEL_TYPE})")
        print()
        return

    # 加载历史数据
    print("📊 加载历史开奖数据...")
    history = load_history()
    if not history or not history.get("data"):
        print("❌ 历史数据为空，请先运行爬虫更新数据")
        return

    target_period, target_date, prediction_date = get_next_draw_info(history)
    if not target_period:
        print("❌ 无法获取下期期号信息")
        return

    models_to_run = None
    if args.models:
        models_to_run = set(m.strip() for m in args.models.split(','))

    print(f"🎯 目标期号: {target_period}")
    print(f"📅 开奖日期: {prediction_date}")

    output = run_all_strategies(
        history, target_period, target_date, prediction_date,
        models_to_run=models_to_run
    )

    if output and output.get("models"):
        save_predictions(output, args.output)
    else:
        print("❌ 没有生成任何预测")
        sys.exit(1)


if __name__ == "__main__":
    main()