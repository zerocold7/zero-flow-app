Set WshShell = CreateObject("WScript.Shell")
' Run the batch file silently (0 means hide window)
WshShell.Run chr(34) & "Launch_Flow.bat" & Chr(34), 0
Set WshShell = Nothing