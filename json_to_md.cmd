@echo off
rem Write manuals as Markdown (md\<id>.md) to read and edit them, e.g. with AI help.
rem Double-click: pick manuals from a list. Or pass ids / --all / --force (see scripts\json_to_md.py).
rem Bring the edits back with md_to_json.cmd.
cd /d "%~dp0"
python scripts\json_to_md.py %*
set rc=%errorlevel%
if "%~1"=="" pause
exit /b %rc%
