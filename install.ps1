param([switch]$Voicebox, [switch]$Demo)
$ErrorActionPreference = 'Stop'
$deps = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'dependencies.json') | ConvertFrom-Json

function Install-Dependency($package) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet is required to install missing tools. See SETUP.txt.'
    }
    & winget.exe install --id $package --exact --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "WinGet failed for $package with code $LASTEXITCODE." }
    $env:Path = @($env:Path, [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')) -join ';'
}

function Get-PythonCommand {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $savedPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $launcher.Source -3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) { return @($launcher.Source, '-3') }
        } finally { $ErrorActionPreference = $savedPreference }
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and $python.Source -notlike '*\Microsoft\WindowsApps\*') {
        & $python.Source -c 'import sys; sys.exit(sys.version_info < (3, 10))'
        if ($LASTEXITCODE -eq 0) { return @($python.Source) }
    }
}

$pythonCommand = @(Get-PythonCommand)
if (-not $pythonCommand) {
    Install-Dependency $deps.windows.python
    $pythonCommand = @(Get-PythonCommand)
}
if (-not $pythonCommand) { throw 'Python 3.10+ was not detected. Reopen PowerShell and retry.' }
$node = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $node -or [int](& $node.Source -p 'parseInt(process.versions.node)') -lt 22) {
    Install-Dependency $deps.windows.node
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    Install-Dependency $deps.windows.ffmpeg
}

$arguments = @($pythonCommand | Select-Object -Skip 1) + @(Join-Path $PSScriptRoot 'setup_dependencies.py')
if ($Voicebox) { $arguments += '--voicebox' }
if ($Demo) { $arguments += '--demo' }
& $pythonCommand[0] @arguments
exit $LASTEXITCODE
