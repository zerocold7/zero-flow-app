' Start the merged engine invisibly (0 means hide window). Exit from its tray icon.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName) & "\"

WshShell.Run chr(34) & base & "Launch_Zero.bat" & chr(34), 0

Set fso = Nothing
Set WshShell = Nothing
