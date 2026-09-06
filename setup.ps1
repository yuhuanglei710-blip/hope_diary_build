[CmdletBinding()]
param(
    [switch]$NoLaunch,
    [switch]$BuildExe,
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Python {
    $probe = 'import sys, tkinter; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            & $launcher.Source -3.12 -c $probe
            if ($LASTEXITCODE -eq 0) {
                return @{ Exe = $launcher.Source; Args = @("-3.12") }
            }
        } catch {}
    }

    $knownPythons = @(
        (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )
    foreach ($knownPython in $knownPythons) {
        if (Test-Path -LiteralPath $knownPython) {
            try {
                & $knownPython -c $probe
                if ($LASTEXITCODE -eq 0) { return @{ Exe = $knownPython; Args = @() } }
            } catch {}
        }
    }

    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            try {
                & $command.Source -c $probe
                if ($LASTEXITCODE -eq 0) {
                    return @{ Exe = $command.Source; Args = @() }
                }
            } catch {}
        }
    }

    return $null
}

function Set-TkEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExe,
        [string[]]$PythonArgs = @()
    )

    $basePrefix = & $PythonExe @PythonArgs -c 'import sys; print(sys.base_prefix)'
    $tclVersion = & $PythonExe @PythonArgs -c 'import tkinter; print(tkinter.TclVersion)'
    $tkVersion = & $PythonExe @PythonArgs -c 'import tkinter; print(tkinter.TkVersion)'
    if ($LASTEXITCODE -ne 0 -or -not $basePrefix -or -not $tclVersion -or -not $tkVersion) {
        throw "This Python installation does not include Tkinter. Install the official Python 3.12 distribution and try again."
    }

    $tclRoot = Join-Path ($basePrefix | Select-Object -Last 1) "tcl"
    $tclLibrary = Join-Path $tclRoot ("tcl" + ($tclVersion | Select-Object -Last 1))
    $tkLibrary = Join-Path $tclRoot ("tk" + ($tkVersion | Select-Object -Last 1))
    if (-not (Test-Path -LiteralPath $tclLibrary) -or -not (Test-Path -LiteralPath $tkLibrary)) {
        throw "The Tcl/Tk runtime is incomplete. Reinstall Python with the Tcl/Tk and IDLE feature enabled."
    }

    $env:TCL_LIBRARY = $tclLibrary
    $env:TK_LIBRARY = $tkLibrary
    & $PythonExe @PythonArgs -c 'import tkinter; tkinter.Tcl()'
    if ($LASTEXITCODE -ne 0) { throw "Tkinter could not initialize with this Python installation." }
    Write-Host "Tkinter runtime: $tkLibrary" -ForegroundColor DarkGray
}

Write-Host "[1/4] Checking official Python 3.12 with Tkinter..." -ForegroundColor Cyan
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
    throw "Official Python 3.12 with Tkinter is required. Install it and run setup.ps1 again."
}
Set-TkEnvironment -PythonExe $python.Exe -PythonArgs @($python.Args)

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvRoot = Join-Path $PSScriptRoot ".venv"
if (Test-Path -LiteralPath $venvPython) {
    & $venvPython -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Replacing the existing environment with Python 3.12..." -ForegroundColor Yellow
        Remove-Item -LiteralPath $venvRoot -Recurse -Force
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[2/4] Creating the isolated environment..." -ForegroundColor Cyan
    & $python.Exe @($python.Args) -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python environment." }
} else {
    Write-Host "[2/4] Existing isolated environment found." -ForegroundColor Green
}
Set-TkEnvironment -PythonExe $venvPython

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
