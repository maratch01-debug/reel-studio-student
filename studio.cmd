@echo off
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0studio.py" %*
) else (
    python "%~dp0studio.py" %*
)
exit /b %errorlevel%
