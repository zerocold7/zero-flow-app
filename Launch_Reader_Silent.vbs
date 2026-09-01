Set WshShell = CreateObject("WScript.Shell")
' Run the reader batch file silently (0 means hide window)
WshShell.Run chr(34) & "Launch_Reader.bat" & Chr(34), 0
Set WshShell = Nothing
