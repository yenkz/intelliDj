$ErrorActionPreference = 'Stop'

param(
    [string]$Source = "$HOME/Soulseek/downloads/complete",
    [string]$Config = "$HOME/.config/beets/config.yaml"
)

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir 'beets_import.log'
$lockFile = Join-Path $env:TEMP 'intellidj_beets.lock'

Start-Transcript -Path $logFile -Append | Out-Null
try {
    if (Test-Path $lockFile) {
        exit 0
    }

    New-Item -ItemType File -Path $lockFile -Force | Out-Null
    try {
        $files = Get-ChildItem -Path $Source -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -match '^(?i)\.(mp3|flac|wav|aiff)$' }

        if ($files.Count -gt 0) {
            poetry run beet -c $Config import -q -s $Source
        }
    }
    finally {
        Remove-Item -Path $lockFile -ErrorAction SilentlyContinue
    }
}
finally {
    Stop-Transcript | Out-Null
}
