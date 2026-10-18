@echo off
title AI Job Agent - 24/7 Autonomous Controller
cd /d "%~dp0"

echo ===================================================
echo     STARTING AI JOB AGENT (AUTONOMOUS 24/7)
echo ===================================================
echo.
echo [1/2] Launching Telegram Listener in Background...
start "Telegram Listener" /min py backend\telegram_listener.py

echo [2/2] Launching 24/7 Autonomous Background Agent...
start "Autonomous Agent Loop" py backend\antigravity_agent.py

echo.
echo ===================================================
echo  Both services are now running!
echo  - Jobs will be scraped and matched every 2 hours.
echo  - Approval cards will be sent to your Telegram.
echo  You can minimize these windows.
echo ===================================================
timeout /t 5
