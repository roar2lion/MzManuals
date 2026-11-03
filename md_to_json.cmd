@echo off
rem Put edited Markdown (md\<id>.md) back into the manuals' JSON, then validate it.
rem Double-click: pick files from a list. Or pass ids / --all / --yes (see scripts\md_to_json.py).
rem If the result doesn't validate, the JSON is left as it was and the problems are listed.
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python scripts\md_to_json.py %*
set rc=%errorlevel%
if "%~1"=="" pause
exit /b %rc%
