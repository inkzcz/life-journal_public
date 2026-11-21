@echo off
setlocal
chcp 65001 >nul
 title Life Journal Local Release
 echo Life Journal local Docker TAR release tool
 powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0release-local.ps1" %*
 set "release_result=%ERRORLEVEL%"
 echo.
 if not "%release_result%"=="0" echo Release failed. Keep the error details above. Do not deploy partial files.
 pause
 exit /b %release_result%
