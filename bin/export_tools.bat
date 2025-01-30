@echo off
setlocal enabledelayedexpansion

:: Usage: collect_tools.bat <container_id_or_name> <destination_directory>
set "CONTAINER_ID=%~1"
set "DEST_DIR=%~2"

if "%CONTAINER_ID%"=="" goto :usage
if "%DEST_DIR%"=="" goto :usage

mkdir "%DEST_DIR%" 2>nul

docker exec %CONTAINER_ID% tar -czf - ^
  -C / ^
  usr/local/bin/cloc ^
  usr/local/bin/go-enry ^
  usr/local/bin/kantra ^
  usr/local/bin/grype ^
  usr/local/bin/syft ^
  usr/local/bin/trivy ^
  home/airflow ^
> "%DEST_DIR%\tools.tar.gz"

echo tools.tar.gz has been saved to %DEST_DIR%\tools.tar.gz
goto :eof

:usage
echo Usage: %~nx0 ^<container_id_or_name^> ^<destination_directory^>
exit /b 1
