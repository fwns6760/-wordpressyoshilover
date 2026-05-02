param(
    [string]$TaskName = "YOSHILOVER-Claude-State-Check",
    [string]$Distro = "Ubuntu",
    [string]$RepoPath = "/home/fwns6/code/wordpressyoshilover",
    [ValidateSet("dry-run", "run")]
    [string]$Mode = "dry-run",
    [int]$IntervalMinutes = 30,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$script = "$RepoPath/scripts/ops/claude_state_check_runner.sh --$Mode"
$bashCommand = "cd $RepoPath && $script"
$taskRun = "wsl.exe -d $Distro -- bash -lc `"$bashCommand`""

Write-Host "TaskName: $TaskName"
Write-Host "IntervalMinutes: $IntervalMinutes"
Write-Host "Command: $taskRun"

if ($WhatIf) {
    Write-Host "WhatIf: not registering task."
    exit 0
}

$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d $Distro -- bash -lc `"$bashCommand`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "YOSHILOVER local Claude state check runner ($Mode)" -Force | Out-Null

Write-Host "Registered: $TaskName"
