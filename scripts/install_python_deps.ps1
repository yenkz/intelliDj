$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir 'install_python_deps.log'

Start-Transcript -Path $logFile -Append | Out-Null
try {
    if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
        py -m pip install poetry
    }

    poetry install --no-root
}
finally {
    Stop-Transcript | Out-Null
}
