param(
    [Parameter(Mandatory = $true)]
    [string]$LocalWpPath,

    [ValidateSet('all', 'theme', 'plugin')]
    [string]$SyncTarget = 'all',

    [switch]$Watch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$timestamp] $Message"
}

function Resolve-ExistingDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required path does not exist: $Path"
    }

    $item = Get-Item -LiteralPath $Path
    if (-not $item.PSIsContainer) {
        throw "Expected directory path: $Path"
    }

    return $item.FullName
}

function Ensure-RealDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        return
    }

    $item = Get-Item -LiteralPath $Path -Force
    if ($item.LinkType) {
        throw "Target path is a link. Replace it with a real directory before syncing: $Path"
    }

    if (-not $item.PSIsContainer) {
        throw "Target path is not a directory: $Path"
    }
}

function Sync-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    Ensure-RealDirectory -Path $Destination
    Write-Log "Syncing $Label"
    $robocopyArgs = @(
        $Source,
        $Destination,
        '/MIR',
        '/FFT',
        '/R:2',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NP',
        '/XD', '.git', '.svn', '__pycache__'
    )
    & robocopy @robocopyArgs | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -gt 7) {
        throw "robocopy failed for $Label with exit code $exitCode"
    }
}

function Start-Watcher {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path = $Source
    $watcher.IncludeSubdirectories = $true
    $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, DirectoryName, LastWrite, CreationTime'
    $watcher.EnableRaisingEvents = $true

    $state = [pscustomobject]@{
        Source      = $Source
        Destination = $Destination
        Label       = $Label
        LastSyncUtc = [datetime]::MinValue
    }

    $action = {
        $eventState = $Event.MessageData
        $nowUtc = [datetime]::UtcNow
        if (($nowUtc - $eventState.LastSyncUtc).TotalMilliseconds -lt 500) {
            return
        }

        $eventState.LastSyncUtc = $nowUtc
        Start-Sleep -Milliseconds 250
        try {
            Sync-Directory -Source $eventState.Source -Destination $eventState.Destination -Label $eventState.Label
        } catch {
            Write-Host "[watch-error] $($_.Exception.Message)"
        }
    }

    $registrations = @(
        (Register-ObjectEvent -InputObject $watcher -EventName Changed -MessageData $state -Action $action)
        (Register-ObjectEvent -InputObject $watcher -EventName Created -MessageData $state -Action $action)
        (Register-ObjectEvent -InputObject $watcher -EventName Deleted -MessageData $state -Action $action)
        (Register-ObjectEvent -InputObject $watcher -EventName Renamed -MessageData $state -Action $action)
    )

    return [pscustomobject]@{
        Watcher       = $watcher
        Registrations = $registrations
        Label         = $Label
    }
}

function Stop-WatcherSet {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$WatcherSets
    )

    foreach ($watcherSet in $WatcherSets) {
        foreach ($registration in $watcherSet.Registrations) {
            Unregister-Event -SourceIdentifier $registration.Name -ErrorAction SilentlyContinue
            Remove-Job -Id $registration.Id -Force -ErrorAction SilentlyContinue
        }
        $watcherSet.Watcher.Dispose()
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$repoTheme = Resolve-ExistingDirectory -Path (Join-Path $repoRoot 'Wordpress\wp-content\themes\marketlense')
$repoPlugin = Resolve-ExistingDirectory -Path (Join-Path $repoRoot 'Wordpress\wp-content\plugins\marketlense-core')
$localWpRoot = Resolve-ExistingDirectory -Path $LocalWpPath
$localTheme = Join-Path $localWpRoot 'wp-content\themes\marketlense'
$localPlugin = Join-Path $localWpRoot 'wp-content\plugins\marketlense-core'

$targets = @()
if ($SyncTarget -in @('all', 'theme')) {
    $targets += [pscustomobject]@{
        Source = $repoTheme
        Destination = $localTheme
        Label = 'theme marketlense'
    }
}
if ($SyncTarget -in @('all', 'plugin')) {
    $targets += [pscustomobject]@{
        Source = $repoPlugin
        Destination = $localPlugin
        Label = 'plugin marketlense-core'
    }
}

foreach ($target in $targets) {
    Sync-Directory -Source $target.Source -Destination $target.Destination -Label $target.Label
}

Write-Log 'Initial sync complete'

if (-not $Watch) {
    return
}

$watcherSets = @()
foreach ($target in $targets) {
    $watcherSets += Start-Watcher -Source $target.Source -Destination $target.Destination -Label $target.Label
}

Write-Log 'Watch mode active. Press Ctrl+C to stop.'
try {
    while ($true) {
        Wait-Event -Timeout 1 | Out-Null
    }
} finally {
    Stop-WatcherSet -WatcherSets $watcherSets
}
