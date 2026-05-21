Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c lms server start --port 1233", 0, False