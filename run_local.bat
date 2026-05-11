@echo off
REM ───────────────────────────────────────────────────────────
REM  BOM Generator — Local Launcher
REM  Double-click ไฟล์นี้เพื่อเปิดแอป
REM ───────────────────────────────────────────────────────────

cd /d "%~dp0"

echo Starting BOM Generator...
echo URL: http://localhost:8501
echo.
echo กด Ctrl+C เพื่อหยุดเซิร์ฟเวอร์
echo.

py -m streamlit run app.py --server.headless true
pause
