@echo off
cd /d "%~dp0"
title Voice Labeling Workbench
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys" >nul 2>&1
if not errorlevel 1 goto run_python
echo.
echo   Python 3 not found on this machine.
echo   Install Python 3 first, then run this file again.
echo.
pause
exit /b 1

:run_py
py -3 "tools\_launcher.py"
goto done

:run_python
python "tools\_launcher.py"
goto done

:done
echo.
pause
