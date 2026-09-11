Set shell = CreateObject("WScript.Shell")
probeRoot = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & probeRoot & "\run_probe.ps1"""
shell.Run cmd, 0, False
