@echo off
REM 双击即可更新 ETF 数据到 GitHub
cd /d "%~dp0"
python update.py %*
pause
