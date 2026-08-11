#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 AI 预测脚本功能"""

import json

def test_prediction_file():
    """测试预测文件格式"""
    print("=" * 50)
    print("测试 AI 预测数据文件")
    print("=" * 50 + "\n")
    
    try:
        with open("data/ai_predictions.json", "r", encoding="utf-8") as f:
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
        
        # 检查每个模型
        for model in models:
            model_name = model.get("model_name", "未知")
            predictions = model.get("predictions", [])
            
            # 检查预测组数量
            assert len(predictions) == 4, f"{model_name} 预测组数量不正确: {len(predictions)}"
            
            # 检查每组预测
            for pred in predictions:
                front_balls = pred.get("front_balls", [])
                back_balls = pred.get("back_balls", [])

                # 前区检查（5个，01-35）
                assert len(front_balls) == 5, f"{model_name} 前区数量不正确: {len(front_balls)}"
                assert front_balls == sorted(front_balls), f"{model_name} 前区未排序"
                for b in front_balls:
                    assert 1 <= int(b) <= 35, f"{model_name} 前区号码超出范围: {b}"

                # 后区检查（2个，01-12）
                assert len(back_balls) == 2, f"{model_name} 后区数量不正确: {len(back_balls)}"
                assert back_balls == sorted(back_balls), f"{model_name} 后区未排序"
                for b in back_balls:
                    assert 1 <= int(b) <= 12, f"{model_name} 后区号码超出范围: {b}"

            print(f"   ✓ {model_name}: 4 组预测，格式正确")
        
        print("\n" + "=" * 50)
        print("✅ 所有测试通过！")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        raise

if __name__ == "__main__":
    test_prediction_file()
