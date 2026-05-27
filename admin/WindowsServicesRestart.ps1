# WindowsServicesRestart.ps1
# Purpose: At boot, after a short delay, ensure specified ArcGIS services are running,
# but only start them if their startup type is Automatic (or DelayedAutoStart).
# Run as SYSTEM or an Administrator via Scheduled Task at system startup.
param(
    [string[]]$ServiceNames = @("ArcGISServer", "ArcGISDataStore"), # replace with actual service Names
    [int]$LogRetentionDays = 30
)

$logDir = "C:\ProgramData\ArcGIS\start-check"
if (-not (Test-Path $logDir)) { New-Item -Path $logDir -ItemType Directory -Force | Out-Null }
$logFile = Join-Path $logDir ("startup-check-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

function Log {
    param($msg)
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $msg
    Add-Content -Path $logFile -Value $line
    Write-Output $line
}

Log "Starting ArcGIS services check. Checking services: $($ServiceNames -join ', ')"

foreach ($svcName in $ServiceNames) {
    # Get service object & Win32 info
    $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Log "Service '$svcName' not found. Skipping."
        continue
    }
    $wmi = Get-WmiObject -Class Win32_Service -Filter "Name='$svcName'"
    $startMode = $wmi.StartMode  # Automatic, Manual, Disabled

    Log "Service: $svcName  DisplayName: $($svc.DisplayName)  StartMode: $startMode  Status: $($svc.Status)"

    if ($startMode -eq "Disabled") {
        Log " - Service is Disabled. Not attempting to start."
        continue
    }
    if ($startMode -eq "Manual") {
        Log " - Service is Manual. Assuming intentional. Not attempting to start."
        continue
    }

    if ($svc.Status -ne "Running") {
        try {
            Log " - Attempting to start service '$svcName'..."
            Start-Service -Name $svcName -ErrorAction Stop
            # Wait a short time to confirm
            $svc | Wait-Service -Timeout 30
            Log " - Service '$svcName' started successfully."
        } catch {
            Log " - Failed to start service '$svcName': $_"
        }
    } else {
        Log " - Service already running."
    }
}

# Cleanup old logs
try {
    Get-ChildItem -Path $logDir -Filter "startup-check-*.log" |
      Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-$LogRetentionDays) } |
      Remove-Item -Force -ErrorAction SilentlyContinue
} catch {
    Log " - Log cleanup error: $_"
}

Log "ArcGIS services check completed."