$startSink = 'C:\Users\hct\.ma3\probe\start_sink.ps1'
$task = 'ma3-alert-sink'
schtasks /Query /TN $task 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { schtasks /Delete /TN $task /F | Out-Null }
$cmd = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $startSink + '"'
schtasks /Create /TN $task /TR $cmd /SC ONLOGON /RU hct /F
schtasks /Query /TN $task /FO LIST | Select-String 'TaskName|Status|Task To Run'
