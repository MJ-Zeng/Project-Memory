@echo off
setlocal EnableExtensions
rem project-memory trusted entry (Windows).
rem
rem A pip "module:function" console_script resolves a top-level module through
rem the ambient sys.path BEFORE any isolation, so a same-named file on
rem PYTHONPATH/cwd runs first (B5A.1).  This native wrapper cannot be preempted
rem that way: it establishes interpreter isolation (-I -P) at the OS level, then
rem runs the launcher BY ABSOLUTE PATH -- never as an importable module name.
rem
rem See docs/decisions/ADR-0005-cli-bootstrap.md.

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "LAUNCHER="
if exist "%HERE%\_project_memory_launcher.py" set "LAUNCHER=%HERE%\_project_memory_launcher.py"
if not defined LAUNCHER if exist "%HERE%\..\_project_memory_launcher.py" set "LAUNCHER=%HERE%\..\_project_memory_launcher.py"
if not defined LAUNCHER (
    echo project-memory: cannot locate the trusted launcher script 1>&2
    exit /b 3
)

rem Choose a trusted interpreter: explicit override, then a venv sibling, then PATH.
set "PY=%PROJECT_MEMORY_PYTHON%"
if not defined PY if exist "%HERE%\python.exe" set "PY=%HERE%\python.exe"
if not defined PY if exist "%HERE%\..\python.exe" set "PY=%HERE%\..\python.exe"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PY (
    echo project-memory: no Python interpreter found 1>&2
    exit /b 3
)

rem Not a bare exit: a PATH stub (the Windows Store python alias) exits 49 silently.
rem "call" is required so a .bat/.cmd shim (pyenv-win) returns to this script.
call "%PY%" -I -P "%LAUNCHER%" %*
set "STATUS=%ERRORLEVEL%"
if "%STATUS%"=="0" exit /b 0
call "%PY%" -c "import sys" >nul 2>&1
if not errorlevel 1 exit /b %STATUS%
echo project-memory: interpreter is not runnable: %PY% (exit %STATUS%) 1>&2
echo project-memory: set PROJECT_MEMORY_PYTHON to a working Python 3.11+ 1>&2
exit /b 3
