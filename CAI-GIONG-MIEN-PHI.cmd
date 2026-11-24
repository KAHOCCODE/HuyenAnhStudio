@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set HF_HUB_DISABLE_TELEMETRY=1
set DO_NOT_TRACK=1
set GRADIO_ANALYTICS_ENABLED=False
echo === HUYEN ANH STUDIO - CAI 25 GIONG VIET MIEN PHI ===
echo Bo giong VieNeu CPU, khong API key va khong han muc ky tu moi ngay.
echo Can mang de cai thu vien. Mo hinh duoc tai khi tao cau dau tien.
if exist ".tts-venv\Scripts\python.exe" goto dependencies
for %%V in (3.11 3.12 3.13) do (
    py -%%V -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
    if not errorlevel 1 (
        py -%%V -m venv .tts-venv
        goto dependencies
    )
)
python -c "import sys,struct; assert (3,11) <= sys.version_info[:2] <= (3,13); assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto nopython
python -m venv .tts-venv
:dependencies
if not exist ".tts-venv\Scripts\python.exe" goto failed
".tts-venv\Scripts\python.exe" tools\install_local_tts.py
if errorlevel 1 goto failed
echo.
echo CAI XONG. Mo start.cmd, chon giong VieNeu va nghe thu mot cau.
echo Cac lan sau dung lai mo hinh, khong tinh phi theo ky tu.
pause
exit /b 0
:nopython
echo Can Python 3.11, 3.12 hoac 3.13 ban 64-bit.
echo Cai Python tu python.org roi chay lai.
pause
exit /b 1
:failed
echo.
echo CAI CHUA HOAN TAT. Xem loi phia tren roi chay lai file nay.
pause
exit /b 1
