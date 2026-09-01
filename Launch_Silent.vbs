' Run the dictation half invisibly (0 means hide window). Stop it from its tray icon.
' Paths are resolved from this script's own folder, not the working directory, so it
' works when launched from a shortcut, the Startup folder, or Task Scheduler.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName) & "\"

WshShell.Run chr(34) & base & "Launch_Flow.bat" & chr(34), 0

Set fso = Nothing
Set WshShell = Nothing
