#!/bin/bash
echo "===================================================="
echo "  大乐透 AI 预测 - 本地一键更新"
echo "===================================================="
echo

# 1. 拉取最新代码
echo "[1/5] 拉取最新代码..."
git pull origin master
echo

# 2. 抓取最新开奖数据
echo "[2/5] 抓取最新开奖数据..."
python3 fetch_history/fetch_lottery_history.py
if [ $? -ne 0 ]; then
    echo "[错误] 数据抓取失败"
    exit 1
fi
echo

# 3. 运行模型预测
echo "[3/5] 运行统计/ML 模型预测..."
python3 -m strategies.runner
if [ $? -ne 0 ]; then
    echo "[错误] 模型预测失败"
    exit 1
fi
echo

# 4. 检查变更
echo "[4/5] 检查数据变更..."
if git diff --quiet data/ fetch_history/ 2>/dev/null; then
    echo "无新数据变更，跳过提交"
    echo
    echo "===================================================="
    echo "  检查完成，数据已是最新"
    echo "===================================================="
    exit 0
fi

echo "发现数据变更，准备提交..."
echo

# 5. 提交并推送
echo "[5/5] 提交并推送..."
git add data/ fetch_history/
git commit -m "chore: manual update $(date '+%Y-%m-%d %H:%M:%S')"
git push origin master
if [ $? -ne 0 ]; then
    echo "[错误] git push 失败"
    exit 1
fi

echo
echo "===================================================="
echo "  更新完成！数据已同步到 GitHub"
echo "  本地访问: http://localhost:8000"
echo "===================================================="
