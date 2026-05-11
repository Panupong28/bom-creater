@echo off
REM ───────────────────────────────────────────────────────────
REM  BOM Generator — One-time Setup
REM  รันครั้งเดียวตอนเริ่มใช้เครื่องใหม่
REM ───────────────────────────────────────────────────────────

cd /d "%~dp0"

echo Installing Python packages...
py -m pip install --user --upgrade -r requirements.txt

echo.
echo Setup เสร็จแล้ว — ดับเบิลคลิก run_local.bat เพื่อเปิดแอป
pause
