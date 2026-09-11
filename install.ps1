# Installs the RAGpilot CLI: downloads the source for $env:RAGPILOT_REF
# (default: main), creates an isolated virtual environment, installs the
# package into it, and puts a `ragpilot` launcher on a per-user bin
# directory added to the user's PATH.
#
# Requires Python 3.12+ already on PATH -- this script does not install
# Python itself. See README.md's Installation section for details.

$ErrorActionPreference = "Stop"

$Repo = "gzarog/Ragpilotv2"
$Ref = if ($env:RAGPILOT_REF) { $env:RAGPILOT_REF } else { "main" }
$InstallDir = if ($env:RAGPILOT_INSTALL_DIR) { $env:RAGPILOT_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "RAGpilot" }
$AppDir = Join-Path $InstallDir "app"
$VenvDir = Join-Path $InstallDir "venv"
$BinDir = if ($env:RAGPILOT_BIN_DIR) { $env:RAGPILOT_BIN_DIR } else { Join-Path $InstallDir "bin" }

function Find-Python {
    # Each candidate is a hashtable { Exe; Args } rather than a flat array --
    # PowerShell's `1..0` range operator returns @(1, 0), not an empty array,
    # which would break slicing off "the rest" of a single-element array.
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += , @{ Exe = "py"; Args = @("-3.12") }
        $candidates += , @{ Exe = "py"; Args = @("-3") }
    }
    foreach ($name in @("python3.12", "python3", "python")) {
        if (Get-Command $name -ErrorAction SilentlyContinue) {
            $candidates += , @{ Exe = $name; Args = @() }
        }
    }
    foreach ($c in $candidates) {
        try {
            $ver = & $c.Exe @($c.Args) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ver) {
                $parts = $ver.Trim().Split(".")
                if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 12) {
                    return $c
                }
            }
        } catch {}
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Write-Error "RAGpilot requires Python 3.12+, but no suitable interpreter was found on PATH.`nInstall Python 3.12 or newer (https://www.python.org/downloads/) and re-run this script."
    exit 1
}
$pythonVersion = & $Python.Exe @($Python.Args) --version
Write-Host "Using $pythonVersion at $($Python.Exe) $($Python.Args -join ' ')"

Write-Host "Downloading RAGpilot ($Ref)..."
$ZipPath = Join-Path ([System.IO.Path]::GetTempPath()) "ragpilot-$([guid]::NewGuid()).zip"
$DownloadUrl = "https://github.com/$Repo/archive/refs/heads/$Ref.zip"
# GitHub's archive/codeload endpoint can briefly 404 a branch that was just
# pushed (its zipball cache lags the push by a few seconds) -- retry a
# handful of times with linear backoff before giving up, rather than
# failing outright on what is usually a transient race.
$maxAttempts = 5
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath -UseBasicParsing
        break
    } catch {
        if ($attempt -ge $maxAttempts) {
            Write-Error "Failed to download $DownloadUrl after $attempt attempts: $_"
            exit 1
        }
        Write-Host "Download attempt $attempt failed, retrying in ${attempt}s..."
        Start-Sleep -Seconds $attempt
    }
}

$ExtractRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ragpilot-extract-$([guid]::NewGuid())"
Expand-Archive -Path $ZipPath -DestinationPath $ExtractRoot -Force
Remove-Item -Force $ZipPath

$ExtractedDir = Get-ChildItem -Path $ExtractRoot -Directory | Select-Object -First 1
if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
New-Item -ItemType Directory -Force -Path (Split-Path $AppDir -Parent) | Out-Null
Move-Item -Path $ExtractedDir.FullName -Destination $AppDir
Remove-Item -Recurse -Force $ExtractRoot

Write-Host "Creating virtual environment at $VenvDir..."
if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir }
& $Python.Exe @($Python.Args) -m venv $VenvDir

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
Write-Host "Installing RAGpilot (this downloads its dependencies, including torch -- may take a few minutes)..."
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet $AppDir

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$LauncherPath = Join-Path $BinDir "ragpilot.cmd"
$VenvRagpilot = Join-Path $VenvDir "Scripts\ragpilot.exe"
"@echo off`r`n`"$VenvRagpilot`" %*" | Set-Content -Path $LauncherPath -Encoding ASCII
Write-Host "RAGpilot installed: $LauncherPath"

$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if (";$UserPath;" -notlike "*;$BinDir;*") {
    $NewPath = if ($UserPath) { "$UserPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("PATH", $NewPath, "User")
    Write-Host ""
    Write-Host "Added $BinDir to your user PATH. Open a new terminal for this to take effect."
}

Write-Host ""
Write-Host "Run 'ragpilot version' to verify, then 'ragpilot init' to get started."
