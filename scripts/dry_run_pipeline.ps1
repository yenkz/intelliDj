$ErrorActionPreference = 'Stop'

param(
    [string]$Csv = 'spotify_export.csv',
    [string]$Candidates = 'dj_candidates.csv',
    [string]$DownloadsDir = "$HOME/Soulseek/downloads/complete",
    [string]$BeetsConfig = "$HOME/.config/beets/config.yaml",
    [string]$LibraryDir = "$HOME/Music/DJ/library",
    [switch]$NoTags,
    [switch]$NoBeets,
    [switch]$NoLoudnorm
)

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir 'dry_run_pipeline.log'

Start-Transcript -Path $logFile -Append | Out-Null
try {
    Write-Host '==> Dry-run pipeline'
    Write-Host "CSV: $Csv"
    Write-Host "Candidates: $Candidates"
    Write-Host "Downloads: $DownloadsDir"
    Write-Host "Beets config: $BeetsConfig"
    Write-Host "Library: $LibraryDir"
    Write-Host ''

    Write-Host '==> Step 1: Generate candidates'
    poetry run python csv_to_dj_pipeline.py --input $Csv --output $Candidates

    Write-Host ''
    Write-Host '==> Step 2: slskd download (dry-run)'
    poetry run python dj_to_slskd_pipeline.py --csv $Candidates --dry-run

    if (-not $NoTags) {
        Write-Host ''
        Write-Host '==> Step 3: Tag enrichment (dry-run)'
        poetry run python scripts/enrich_tags_from_spotify_csv.py --csv $Csv --input-dir $DownloadsDir --custom-tags --dry-run
    }

    if (-not $NoBeets) {
        Write-Host ''
        Write-Host '==> Step 4: Beets import (preview)'
        poetry run beet -c $BeetsConfig import -p -s $DownloadsDir
    }

    if (-not $NoLoudnorm) {
        Write-Host ''
        Write-Host '==> Step 5: Loudnorm (dry-run)'
        powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'normalize_loudness.ps1') -InputDir $LibraryDir -DryRun
    }

    Write-Host ''
    Write-Host 'Done. Dry-run complete.'
}
finally {
    Stop-Transcript | Out-Null
}
