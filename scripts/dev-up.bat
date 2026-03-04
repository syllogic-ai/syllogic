@echo off
REM Wrapper script to run dev-up.ps1 with proper execution policy
REM Usage: dev-up.bat [local|prebuilt]

set MODE=%1
if "%MODE%"=="" set MODE=local

powershell.exe -ExecutionPolicy Bypass -File "%~dp0dev-up.ps1" -Mode %MODE% %2 %3 %4
