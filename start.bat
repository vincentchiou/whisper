@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Whisper

echo ================================
echo  Whisper SRT - Starting...
echo ================================
echo.

echo [CHECK] Checking localhost:5000...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); if ($p.CommandLine -match 'app\.py') { Write-Host '[INFO] Stopping old Whisper server on port 5000...'; Stop-Process -Id $c.OwningProcess -Force; Start-Sleep -Seconds 1; exit 0 } else { Write-Host '[ERROR] Port 5000 is used by another program:'; Write-Host $p.CommandLine; exit 2 } }"
if errorlevel 2 (
    echo.
    echo [ERROR] Please close the program above, then run start.bat again.
    echo.
    pause
    exit /b 1
)
echo.

set "PYTHON_EXE="
set "BASE_PYTHON_CMD="
set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS_FILE=%~dp0requirements.txt"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONUTF8=1"

:: Prefer PyTorch-compatible Python versions on Windows.
call :find_compatible_py_launcher
if defined BASE_PYTHON_CMD goto ensure_venv

:: Test system python, but skip versions that PyTorch Windows wheels do not support.
python -m pip --version >nul 2>&1
if not errorlevel 1 (
        call :check_python_supported python
        if not errorlevel 1 (
            set "BASE_PYTHON_CMD=python"
            echo [OK] System Python with pip found
            goto ensure_venv
        )
    echo [SKIP] System Python found, but PyTorch on Windows supports Python 3.9 to 3.12.
    call :print_python_version python
)

:: Fallback: Claude Code built-in Python
set FALLBACK=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if exist "%FALLBACK%" (
    "%FALLBACK%" -m pip --version >nul 2>&1
    if not errorlevel 1 (
        call :check_python_supported "%FALLBACK%"
        if not errorlevel 1 (
            set "BASE_PYTHON_CMD="%FALLBACK%""
            echo [OK] Built-in Python found
            goto ensure_venv
        )
    )
)

echo.
echo [ERROR] No compatible Python + pip found!
echo.
echo Please install Python 3.10, 3.11, or 3.12 from:
echo   https://www.python.org/downloads/
echo.
echo IMPORTANT: Check "Add Python to PATH" during install.
echo After installing, run this file again.
echo.
pause
exit /b 1

:ensure_venv
if exist "%VENV_PYTHON%" (
    set "PYTHON_EXE=%VENV_PYTHON%"
    echo [OK] Using project virtual environment
    goto check_flask
)

echo [SETUP] Creating project virtual environment...
echo [SETUP] Base Python: %BASE_PYTHON_CMD%
if exist "%VENV_DIR%" (
    echo [SETUP] Rebuilding incomplete project virtual environment...
)
call :run_ok %BASE_PYTHON_CMD% -m venv "%VENV_DIR%" --clear
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create .venv
    echo Try: %BASE_PYTHON_CMD% -m venv "%VENV_DIR%"
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo.
    echo [ERROR] .venv was created incompletely.
    echo Please delete ".venv" and run start.bat again.
    echo.
    pause
    exit /b 1
)

set "PYTHON_EXE=%VENV_PYTHON%"
echo [OK] Project virtual environment created
echo.

:check_flask
echo [Python] %PYTHON_EXE%
echo.
"%PYTHON_EXE%" -c "import flask" >nul 2>&1
if not errorlevel 1 goto check_gpu

echo [INSTALL] Installing packages (first time, ~2-3 GB download)...
echo [INSTALL] Do NOT close this window...
echo.
"%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Install failed.
    echo Try: "%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS_FILE%"
    echo.
    pause
    exit /b 1
)
echo.
echo [DONE] Packages installed!
echo.

:check_gpu
:: Check if CUDA is really usable. RTX 50 / Blackwell needs CUDA 12.8 PyTorch wheels.
call :cuda_usable "%PYTHON_EXE%"
if not errorlevel 1 (
    echo [GPU] CUDA detected - GPU acceleration enabled!
    goto start_server
)

where nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo [GPU] No NVIDIA driver detected, using CPU mode.
    goto start_server
)

set CUDA_INDEX=https://download.pytorch.org/whl/cu121
set CUDA_LABEL=CUDA 12.1
"%PYTHON_EXE%" -c "import re, subprocess; out=subprocess.check_output(['nvidia-smi','--query-gpu=name','--format=csv,noheader'], text=True, stderr=subprocess.STDOUT); raise SystemExit(0 if re.search(r'RTX\s*50|RTX\s*5\d\d\d|5060|5070|5080|5090', out, re.I) else 1)" >nul 2>&1
if not errorlevel 1 (
    set CUDA_INDEX=https://download.pytorch.org/whl/cu128
    set CUDA_LABEL=CUDA 12.8
    echo [GPU] RTX 50 series detected, using PyTorch CUDA 12.8 wheels.
)

:: CUDA not available or current PyTorch is incompatible - reinstall GPU PyTorch.
echo [GPU] Installing GPU version of PyTorch (%CUDA_LABEL%)...
echo [GPU] This may take a while (~2 GB), please wait...
echo.
"%PYTHON_EXE%" -m pip install torch --index-url %CUDA_INDEX% --upgrade --force-reinstall --progress-bar off
if errorlevel 1 (
    echo [WARN] GPU PyTorch install failed, using CPU mode.
) else (
    call :cuda_usable "%PYTHON_EXE%"
    if not errorlevel 1 (
        echo [GPU] GPU acceleration enabled!
    ) else (
        echo [WARN] PyTorch installed but CUDA test failed.
        echo [WARN] RTX 50 series requires PyTorch CUDA 12.8 and a recent NVIDIA driver.
        echo [WARN] Continuing in CPU mode...
    )
)
echo.

:start_server
echo [START] Server starting at http://localhost:5000
echo [INFO]  Browser opens in 3 seconds.
echo [INFO]  Close this window to stop.
echo.

start /b cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5000"

"%PYTHON_EXE%" app.py

echo.
if errorlevel 1 (
    echo [ERROR] Server stopped unexpectedly.
) else (
    echo [STOP] Server closed.
)
echo.
pause
exit /b

:check_python_supported
%* -c "import sys; v=sys.version_info; sys.exit(0 if v.major == 3 and 9 <= v.minor <= 12 else 1)" >nul 2>&1
exit /b %errorlevel%

:find_compatible_py_launcher
for %%V in (3.12 3.11 3.10 3.9) do (
    call :try_py_launcher %%V
    if defined BASE_PYTHON_CMD exit /b 0
)
exit /b 1

:try_py_launcher
set "PY_TAG="
for /f "usebackq delims=" %%S in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$v='%~1'; $line = py --list 2>$null | Where-Object { $_ -match ('Python ' + [regex]::Escape($v)) } | Select-Object -First 1; if ($line -and $line -match '-V:([^ ]+)') { $matches[1].Replace('\\','/') }"`) do (
    if not defined PY_TAG set "PY_TAG=%%S"
)

if defined PY_TAG (
    call :run_ok py -V:%PY_TAG% -m pip --version
    if not errorlevel 1 (
        set "BASE_PYTHON_CMD=py -V:%PY_TAG%"
        echo [OK] Python %~1 with pip found
        exit /b 0
    )
)

call :run_ok py -%~1 -m pip --version
if not errorlevel 1 (
    set "BASE_PYTHON_CMD=py -%~1"
    echo [OK] Python %~1 with pip found
    exit /b 0
)
exit /b 1

:print_python_version
%* -c "import sys; print('[SKIP] Current version: Python ' + sys.version.split()[0])"
exit /b %errorlevel%

:run_ok
%* >nul 2>&1
set "LAST_RUN_EXIT=%errorlevel%"
if "%LAST_RUN_EXIT%"=="0" exit /b 0
exit /b 1

:cuda_usable
%* -c "import torch; ok=torch.cuda.is_available(); cc=torch.cuda.get_device_capability(0) if ok else tuple([0,0]); cv=tuple([int(x) for x in (torch.version.cuda or '0.0').split('.')[:2]]); ok=ok and not (cc >= tuple([12,0]) and cv < tuple([12,8])); torch.empty(1, device='cuda') if ok else None; torch.cuda.synchronize() if ok else None; sys_exit=__import__('sys').exit; sys_exit(0 if ok else 1)" >nul 2>&1
exit /b %errorlevel%
