@echo off

echo Starting LM Studio server...
start /min "LM Studio Server" cmd /c lms server start --port 1233

timeout /t 10 /nobreak >nul

echo Loading Gemma model...
lms load google/gemma-4-e4b --gpu=max --context-length=13000 --identifier local-model

timeout /t 10 /nobreak >nul

echo Starting Jarvis GUI...
start "" pythonw gui.py

exit