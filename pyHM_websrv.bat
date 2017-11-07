@echo off

SETLOCAL

SET PYT_EXE=python.exe
SET PYT_OPT=
SET SCR_EXE=%~dp0pyHM_websrv.py
SET SCR_OPT=

REM ------------------------------------------------------------------------------------------------

CLS
%PYT_EXE% %PYT_OPT% %SCR_EXE% %SCR_OPT%
PAUSE

REM ------------------------------------------------------------------------------------------------

ENDLOCAL
