@echo off
rem Entropy installer for Windows.
rem
rem   install.cmd                  interactive installation
rem   install.cmd --help           all options
rem   install.cmd uninstall        remove Entropy
rem
rem Uses the Python bundled in this package; set ENTROPY_PYTHON to use another.
setlocal
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

if defined ENTROPY_PYTHON (
    set "PYTHON=%ENTROPY_PYTHON%"
) else (
    set "PYTHON=%HERE%\python\python.exe"
)

if not exist "%PYTHON%" (
    echo The bundled Python is missing from this package: %PYTHON% 1>&2
    exit /b 1
)

set "PYTHONPATH=%HERE%\application"
"%PYTHON%" -s "%HERE%\application\lib\install\cli.py" --package-root "%HERE%" %*
exit /b %ERRORLEVEL%
