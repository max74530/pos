@echo off
REM run.bat — WEBPOS 一鍵啟動（店員雙擊即用）
cd /d %~dp0
python -m pip install -q flask 2>nul
start "" http://127.0.0.1:5000/
python app.py
pause
