#!/bin/bash

# 大乐透数据展示系统 - 本地服务器启动脚本

echo "=========================================="
echo "大乐透开奖与 AI 预测数据展示系统"
echo "=========================================="
echo ""

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python 3"
    echo "请先安装 Python 3: https://www.python.org/downloads/"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# 切换到项目目录
cd "$SCRIPT_DIR"

echo "✓ 启动本地服务器..."
echo ""
echo "📡 服务器地址: http://localhost:8000"
echo "🌐 请在浏览器中打开上述地址"
echo ""
echo "💡 提示: 按 Ctrl+C 停止服务器"
echo "=========================================="
echo ""

# 启动 Python HTTP 服务器
python3 -m http.server 8000
