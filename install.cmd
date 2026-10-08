@echo off
setlocal
cd /d "%~dp0"
echo === HUYEN ANH STUDIO - CAI DAT ===
echo Can Python 3.11, 3.12 hoac 3.13 va ket noi mang.
if exist ".venv\Scripts\python.exe" goto dependencies
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv .venv
    goto checkenv
)
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    goto checkenv
)
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.13 -m venv .venv
    goto checkenv
)
python -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13)" >nul 2>&1
if errorlevel 1 goto nopython
python -m venv .venv
:checkenv
if not exist ".venv\Scripts\python.exe" goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" check_setup.py
if errorlevel 1 goto failed
echo.
echo CAI DAT XONG. Mo start.cmd de bat dau.
pause
exit /b 0
:nopython
echo Khong tim thay Python 3.11-3.13. Cai Python 64-bit tu python.org.
echo Chon Add Python to PATH trong trinh cai dat.
pause
exit /b 1
:failed
echo.
echo CAI DAT CHUA HOAN TAT. Xem loi phia tren. Khong can xoa du an.
pause
exit /b 1
