$ErrorActionPreference = 'Stop'

param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,
    [switch]$DryRun
)

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir 'normalize_loudness.log'

$targetLufs = if ($env:TARGET_LUFS) { $env:TARGET_LUFS } else { '-9' }
$targetTp = if ($env:TARGET_TP) { $env:TARGET_TP } else { '-1.0' }
$targetLra = if ($env:TARGET_LRA) { $env:TARGET_LRA } else { '9' }

function Get-EncodeArgs([string]$ext) {
    switch ($ext.ToLowerInvariant()) {
        '.flac' { return @('-c:a', 'flac') }
        '.mp3' { return @('-c:a', 'libmp3lame', '-q:a', '2') }
        '.wav' { return @('-c:a', 'pcm_s16le') }
        '.aif' { return @('-c:a', 'pcm_s16be') }
        '.aiff' { return @('-c:a', 'pcm_s16be') }
        default { return @() }
    }
}

Start-Transcript -Path $logFile -Append | Out-Null
try {
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        throw 'ffmpeg not found on PATH.'
    }

    if (-not (Test-Path $InputDir)) {
        throw "Input directory does not exist: $InputDir"
    }

    $normalized = 0
    $skipped = 0
    $errors = 0

    $audioFiles = Get-ChildItem -Path $InputDir -Recurse -File | Where-Object {
        $_.Extension -match '^(?i)\.(flac|mp3|wav|aif|aiff)$'
    }

    if ($audioFiles.Count -eq 0) {
        Write-Host "No audio files found in $InputDir"
        exit 0
    }

    foreach ($file in $audioFiles) {
        if ($DryRun) {
            Write-Host "[dry-run] $($file.FullName)"
            continue
        }

        $analysisOutput = & ffmpeg '-hide_banner' '-nostdin' '-i' $file.FullName '-af' "loudnorm=I=$targetLufs`:TP=$targetTp`:LRA=$targetLra`:print_format=json" '-f' 'null' 'NUL' 2>&1 | Out-String

        $start = $analysisOutput.IndexOf('{')
        $end = $analysisOutput.LastIndexOf('}')
        if ($start -lt 0 -or $end -lt 0 -or $end -le $start) {
            Write-Host "[skip] no loudnorm analysis for: $($file.FullName)"
            $skipped++
            continue
        }

        try {
            $json = $analysisOutput.Substring($start, $end - $start + 1) | ConvertFrom-Json
        }
        catch {
            Write-Host "[skip] invalid loudnorm analysis for: $($file.FullName)"
            $skipped++
            continue
        }

        if (-not $json.input_i -or -not $json.target_offset) {
            Write-Host "[skip] incomplete loudnorm analysis for: $($file.FullName)"
            $skipped++
            continue
        }

        $tmp = Join-Path $file.DirectoryName ('.' + $file.BaseName + '.loudnorm.tmp' + $file.Extension)
        $filter = "loudnorm=I=$targetLufs`:TP=$targetTp`:LRA=$targetLra`:measured_I=$($json.input_i)`:measured_TP=$($json.input_tp)`:measured_LRA=$($json.input_lra)`:measured_thresh=$($json.input_thresh)`:offset=$($json.target_offset)`:linear=true`:print_format=summary"

        $ffmpegArgs = @('-hide_banner', '-nostdin', '-i', $file.FullName, '-map_metadata', '0', '-af', $filter)
        $ffmpegArgs += Get-EncodeArgs $file.Extension
        $ffmpegArgs += $tmp

        & ffmpeg @ffmpegArgs 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[error] loudnorm failed: $($file.FullName)"
            Remove-Item -Path $tmp -ErrorAction SilentlyContinue
            $errors++
            continue
        }

        Move-Item -Path $tmp -Destination $file.FullName -Force
        $normalized++
        Write-Host "[ok] normalized: $($file.FullName)"
    }

    Write-Host ''
    Write-Host "Done. normalized=$normalized skipped=$skipped errors=$errors"
}
finally {
    Stop-Transcript | Out-Null
}
