@echo off

echo Checking LM Studio server...

curl -s http://127.0.0.1:1233/v1/models >nul 2>&1

if %errorlevel%==0 (
    echo LM Studio server already running.
) else (
    echo Starting LM Studio server hidden...
    wscript start_lmstudio_hidden.vbs
    timeout /t 5 /nobreak >nul
)

echo Checking loaded model...

lms ps | findstr /i "local-model" >nul 2>&1

if %errorlevel%==0 (
    echo Model already loaded.
) else (
    echo Loading Gemma model...
    lms load google/gemma-4-e4b --gpu=max --context-length=13000 --identifier local-model
    timeout /t 5 /nobreak >nul
)

echo Starting Jarvis GUI...
start "" pythonw gui.py

exit