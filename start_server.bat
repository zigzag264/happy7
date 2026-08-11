@echo off
REM 大乐透数据展示系统 - 本地服务器启动脚本 (Windows)

echo ==========================================
echo 大乐透开奖与 AI 预测数据展示系统
echo ==========================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X 错误: 未找到 Python
    echo 请先安装 Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo √ 启动本地服务器...
echo.
echo 📡 服务器地址: http://localhost:8000
echo 🌐 请在浏览器中打开上述地址
echo.
echo 💡 提示: 按 Ctrl+C 停止服务器
echo ==========================================
echo.

REM 启动 Python HTTP 服务器
python -m http.server 8000
