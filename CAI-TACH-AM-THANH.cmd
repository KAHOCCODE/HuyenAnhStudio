@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
echo === HUYEN ANH STUDIO - CAI BO TACH AM THANH CPU ===
echo Can ket noi mang. Bo AI duoc cai trong .music-venv.
if exist ".music-venv\Scripts\python.exe" goto dependencies
for %%V in (3.11 3.12 3.13) do (
    py -%%V -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
    if not errorlevel 1 (
        py -%%V -m venv .music-venv
        goto dependencies
    )
)
python -c "import sys,struct; assert (3,11) <= sys.version_info[:2] <= (3,13); assert struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto nopython
python -m venv .music-venv
:dependencies
if not exist ".music-venv\Scripts\python.exe" goto failed
".music-venv\Scripts\python.exe" tools\install_audio_separator.py
if errorlevel 1 goto failed
echo.
echo CAI XONG. Mo start.cmd, chon Xoa giong nhan vat / giu hieu ung.
echo Mo hinh AI se duoc tai trong lan xu ly dau tien.
pause
exit /b 0
:nopython
echo Can Python 3.11, 3.12 hoac 3.13 ban 64-bit.
echo Cai Python tu python.org, chon Add Python to PATH roi chay lai.
pause
exit /b 1
:failed
echo.
echo CAI CHUA HOAN TAT. Xem loi phia tren roi chay lai file nay.
pause
exit /b 1
