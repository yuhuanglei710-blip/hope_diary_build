[CmdletBinding()]
param(
    [switch]$NoLaunch,
    [switch]$BuildExe,
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            & $launcher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
            if ($LASTEXITCODE -eq 0) {
                return @{ Exe = $launcher.Source; Args = @("-3") }
            }
        } catch {}
    }

    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            try {
                & $command.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
                if ($LASTEXITCODE -eq 0) {
                    return @{ Exe = $command.Source; Args = @() }
                }
            } catch {}
        }
    }

    $knownPython = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $knownPython) {
        return @{ Exe = $knownPython; Args = @() }
    }
    return $null
}

Write-Host "[1/4] Checking Python 3.10+..." -ForegroundColor Cyan
$python = Find-Python
if (-not $python -and -not $SkipPythonInstall) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3.10+ was not found, and winget is unavailable. Install Python from https://www.python.org/downloads/ and run this script again."
    }

    Write-Host "Python was not found. Installing Python 3.12 for the current user..." -ForegroundColor Yellow
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "Python installation failed (winget exit code: $LASTEXITCODE)."
    }
    $python = Find-Python
}
if (-not $python) {
    throw "Python 3.10+ is required. Install it and run setup.ps1 again."
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[2/4] Creating the isolated environment..." -ForegroundColor Cyan
    & $python.Exe @($python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python environment." }
} else {
    Write-Host "[2/4] Existing isolated environment found." -ForegroundColor Green
}

Write-Host "[3/4] Installing dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Unable to upgrade pip." }
& $venvPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Unable to install project dependencies." }

if ($BuildExe) {
    Write-Host "[4/4] Building DiaryReplica.exe..." -ForegroundColor Cyan
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --name DiaryReplica --distpath "$PSScriptRoot\dist" --workpath "$PSScriptRoot\build" "$PSScriptRoot\diary_query_gui.py"
    if ($LASTEXITCODE -ne 0) { throw "EXE build failed." }
    Write-Host "Build complete: $PSScriptRoot\dist\DiaryReplica.exe" -ForegroundColor Green
} else {
    Write-Host "[4/4] Environment is ready." -ForegroundColor Green
}

if (-not $NoLaunch) {
    Write-Host "Starting Diary Replica..." -ForegroundColor Cyan
    Start-Process -FilePath $venvPython -ArgumentList "`"$PSScriptRoot\diary_query_gui.py`"" -WorkingDirectory $PSScriptRoot
}
