' Start both halves of the engine invisibly (0 means hide window).
' Each half still gets its own system-tray icon; close it from there.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName) & "\"

WshShell.Run chr(34) & base & "Launch_Flow.bat" & chr(34), 0
WshShell.Run chr(34) & base & "Launch_Reader.bat" & chr(34), 0

Set fso = Nothing
Set WshShell = Nothing
