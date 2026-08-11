#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 AI 预测/策略模型脚本功能"""

import json
import os

def test_prediction_file():
    """测试预测文件格式"""
    print("=" * 50)
    print("测试预测数据文件")
    print("=" * 50 + "\n")

    file_path = "data/ai_predictions.json"
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 基本字段检查
        assert "prediction_date" in data, "缺少 prediction_date 字段"
        assert "target_period" in data, "缺少 target_period 字段"
        assert "models" in data, "缺少 models 字段"

        print(f"✅ 基本字段完整")
        print(f"   预测日期: {data['prediction_date']}")
        print(f"   目标期号: {data['target_period']}\n")

        # 模型数量检查
        models = data["models"]
        print(f"✅ 模型数量: {len(models)}")

        # 统计各模型类型
        type_counts = {}
        for model in models:
            mtype = model.get("model_type", "llm")
            type_counts[mtype] = type_counts.get(mtype, 0) + 1
        for mtype, count in type_counts.items():
            print(f"   - {mtype}: {count} 个")

        print()

        # 检查每个模型
        passed = 0
        failed = 0
        for model in models:
            model_name = model.get("model_name", "未知")
            model_id = model.get("model_id", "未知")
            model_type = model.get("model_type", "llm")
            predictions = model.get("predictions", [])

            errors = []

            # 检查预测组数量（统计模型可为1-4组）
            n_preds = len(predictions)
            if n_preds < 1 or n_preds > 4:
                errors.append(f"预测组数量不正确: {n_preds}")

            # 检查每组预测
            for pred in predictions:
                front_balls = pred.get("front_balls", [])
                back_balls = pred.get("back_balls", [])

                # 前区检查（5个，01-35）
                if len(front_balls) != 5:
                    errors.append(f"前区数量不正确: {len(front_balls)}")
                elif front_balls != sorted(front_balls, key=int):
                    errors.append(f"前区未排序: {front_balls}")
                else:
                    for b in front_balls:
                        if not (1 <= int(b) <= 35):
                            errors.append(f"前区号码超出范围: {b}")
                            break

                # 后区检查（2个，01-12）
                if len(back_balls) != 2:
                    errors.append(f"后区数量不正确: {len(back_balls)}")
                elif back_balls != sorted(back_balls, key=int):
                    errors.append(f"后区未排序: {back_balls}")
                else:
                    for b in back_balls:
                        if not (1 <= int(b) <= 12):
                            errors.append(f"后区号码超出范围: {b}")
                            break

                # 检查前区重复
                if len(set(front_balls)) != 5:
                    errors.append(f"前区有重复号码: {front_balls}")

            if errors:
                failed += 1
                print(f"   ❌ [{model_type}] {model_name}:")
                for e in errors[:3]:
                    print(f"      - {e}")
            else:
                passed += 1
                print(f"   ✓ [{model_type}] {model_name}: {n_preds} 组预测，格式正确")

        print(f"\n{'=' * 50}")
        print(f"✅ 通过: {passed}/{len(models)}")
        if failed:
            print(f"❌ 失败: {failed}/{len(models)}")
        else:
            print(f"✅ 全部通过！")
        print(f"{'=' * 50}")

    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        raise


def test_strategy_models():
    """测试策略模型的输出格式"""
    print("\n" + "=" * 50)
    print("测试策略模型输出格式")
    print("=" * 50 + "\n")

    try:
        from strategies import get_all_strategies
        from strategies.base import load_history, get_next_draw_info, get_recent_draws

        history = load_history()
        history_data = get_recent_draws(history, 30)
        target_period, target_date, prediction_date = get_next_draw_info(history)

        strategies = get_all_strategies(
            history_data, target_period, target_date, prediction_date
        )

        print(f"可用模型: {len(strategies)}")
        for s in strategies:
            try:
                output = s.predict()
                n_preds = len(output.get("predictions", []))
                status = "✅" if n_preds > 0 else "⚠️"
                print(f"  {status} {s.MODEL_NAME:<12s} ({s.MODEL_TYPE:<12s}) → {n_preds} 组预测")
            except Exception as e:
                print(f"  ❌ {s.MODEL_NAME:<12s} 错误: {e}")

        print(f"\n✅ 策略模型测试完成")
    except ImportError as e:
        print(f"❌ 导入策略模块失败: {e}")
        print("   提示: 请确保在项目根目录运行")
    except Exception as e:
        print(f"❌ 测试异常: {e}")


if __name__ == "__main__":
    test_prediction_file()
    test_strategy_models()