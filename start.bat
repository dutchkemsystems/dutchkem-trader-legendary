@echo off
echo ==========================================
echo   DUTCHKEM TRADER - AUTO LAUNCHER
echo ==========================================
echo.
echo Starting FastAPI server + trading engine...
echo.
cd /d "%~dp0backend"
python start_trading.py
pause
