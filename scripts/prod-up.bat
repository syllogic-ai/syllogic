@echo off
REM Wrapper script to run prod-up.ps1 with proper execution policy
powershell.exe -ExecutionPolicy Bypass -File "%~dp0prod-up.ps1" %*
