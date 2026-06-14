@echo off
chcp 65001 >nul
setlocal

REM ============================================
REM  Content Digest — 本地 Runner 入口
REM  配合 Windows 任务计划程序使用
REM  每天 5:30 触发
REM ============================================

REM 切换到脚本所在目录（你的仓库路径）
cd /d "%~dp0"

REM 拉取最新代码
echo [%date% %time%] Pulling latest...
git pull origin main 2>&1
if %errorlevel% neq 0 (
    echo [WARN] git pull failed, continuing anyway
)

REM 运行爬虫 + 日报 + Feed 生成
echo [%date% %time%] Running content digest...
set LOCAL_RUNNER=1
python main.py
if %errorlevel% neq 0 (
    echo [ERROR] python main.py failed
    pause
    exit /b 1
)

REM 推送结果到 GitHub
echo [%date% %time%] Pushing updates...
git add data/content.db data/.last_run output/feed_tech.xml output/feed_life.xml output/feed.xml
git commit -m "Update [local runner]" 2>nul
git push origin main

if %errorlevel% neq 0 (
    echo [WARN] git push failed — will retry next scheduled run
)

echo [%date% %time%] Done.
