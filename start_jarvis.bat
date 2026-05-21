@echo off

echo Starting LM Studio server hidden...
wscript start_lmstudio_hidden.vbs

timeout /t 10 /nobreak >nul

echo Loading Gemma model...
lms load google/gemma-4-e4b --gpu=max --context-length=13000 --identifier local-model

timeout /t 10 /nobreak >nul

echo Starting Jarvis GUI...
start "" pythonw gui.py

exit