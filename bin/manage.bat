@echo off
REM
REM Usage: manage.bat <start|stop|restart> <env> <service>
REM

REM Check if we have exactly 3 arguments
IF [%3]==[] (
    echo Usage: %0 ^<start^|stop^|restart^> ^<env^> ^<service^>
    exit /b 1
)

SET COMMAND=%1
SET ENV_NAME=%2
SET SERVICE=%3

SET ENV_FILE=.env-%ENV_NAME%
SET COMPOSE_FILE=docker-compose-%SERVICE%.yaml
SET PROJECT_NAME=%ENV_NAME%-%SERVICE%

REM Ensure the environment file exists
IF NOT EXIST "%ENV_FILE%" (
    echo Error: Environment file "%ENV_FILE%" not found!
    exit /b 1
)

REM Ensure the Compose file exists
IF NOT EXIST "%COMPOSE_FILE%" (
    echo Error: Docker Compose file "%COMPOSE_FILE%" not found!
    exit /b 1
)

REM Handle the command
IF /I "%COMMAND%"=="start" (
    echo Starting project "%PROJECT_NAME%" using "%ENV_FILE%" and "%COMPOSE_FILE%"...
    docker compose ^
        --project-name "%PROJECT_NAME%" ^
        --env-file "%ENV_FILE%" ^
        -f "%COMPOSE_FILE%" ^
        up -d --build
) ELSE IF /I "%COMMAND%"=="stop" (
    echo Stopping project "%PROJECT_NAME%" using "%ENV_FILE%" and "%COMPOSE_FILE%"...
    docker compose ^
        --project-name "%PROJECT_NAME%" ^
        --env-file "%ENV_FILE%" ^
        -f "%COMPOSE_FILE%" ^
        down
) ELSE IF /I "%COMMAND%"=="restart" (
    echo Restarting project "%PROJECT_NAME%" by stopping then starting...
    REM Stop/down first
    docker compose ^
        --project-name "%PROJECT_NAME%" ^
        --env-file "%ENV_FILE%" ^
        -f "%COMPOSE_FILE%" ^
        down

    REM Start/up again
    docker compose ^
        --project-name "%PROJECT_NAME%" ^
        --env-file "%ENV_FILE%" ^
        -f "%COMPOSE_FILE%" ^
        up -d --build
) ELSE (
    echo Invalid command: %COMMAND%. Valid commands are "start", "stop", or "restart".
    exit /b 1
)
