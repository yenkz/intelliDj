$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir 'install_python_deps_pip.log'

Start-Transcript -Path $logFile -Append | Out-Null
try {
    py -m pip install -r (Join-Path $root 'requirements.txt')
}
finally {
    Stop-Transcript | Out-Null
}
