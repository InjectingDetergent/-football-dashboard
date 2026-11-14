@echo off
setlocal
pushd "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
    python "football_dashboard\build_dashboard.py"
) else (
    py -3 "football_dashboard\build_dashboard.py"
)
if errorlevel 1 (
    pause
) else (
    start "" "%~dp0Football Dashboard.html"
)
popd
