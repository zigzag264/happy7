@echo off
chcp 65001 >nul
echo ====================================================
echo   大乐透 AI 预测 - 本地一键更新
echo ====================================================
echo.

REM 1. 拉取最新代码
echo [1/5] 拉取最新代码...
git pull origin master
if %ERRORLEVEL% neq 0 (
    echo [警告] git pull 失败，继续执行本地更新...
)
echo.

REM 2. 抓取最新开奖数据
echo [2/5] 抓取最新开奖数据...
python fetch_history\fetch_lottery_history.py
if %ERRORLEVEL% neq 0 (
    echo [错误] 数据抓取失败
    pause
    exit /b 1
)
echo.

REM 3. 运行模型预测
echo [3/5] 运行统计/ML 模型预测...
python -m strategies.runner
if %ERRORLEVEL% neq 0 (
    echo [错误] 模型预测失败
    pause
    exit /b 1
)
echo.

REM 4. 检查变更
echo [4/5] 检查数据变更...
git diff --quiet data/ fetch_history/
if %ERRORLEVEL% neq 0 (
    echo 发现数据变更，准备提交...

    REM 5. 提交并推送
    echo [5/5] 提交并推送...
    git add data/ fetch_history/
    git commit -m "chore: manual update %date% %time:~0,8%"
    git push origin master
    if %ERRORLEVEL% neq 0 (
        echo [错误] git push 失败
        pause
        exit /b 1
    )
    echo.
    echo ====================================================
    echo   更新完成！数据已同步到 GitHub
    echo   本地访问: http://localhost:8000
    echo ====================================================
) else (
    echo 无新数据变更，跳过提交
    echo.
    echo ====================================================
    echo   检查完成，数据已是最新
    echo ====================================================
)

pause
