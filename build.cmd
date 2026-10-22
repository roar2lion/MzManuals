@echo off
rem Validate all manuals, build site\ (drafts included) with PDFs, and open it.
rem Pass --check to validate only, or other build.py options (see builder\build.py).
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
if "%~1"=="" (
    python builder\build.py --drafts --pdf
) else (
    python builder\build.py %*
)
if errorlevel 1 (
    echo.
    echo Build failed, see the problems listed above.
    pause
    exit /b 1
)
if exist site\index.html if "%~1"=="" start "" site\index.html
