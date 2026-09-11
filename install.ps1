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
# Same default as ragpilot's own core/paths.py::runtime_dir() on Windows --
# RAGPILOT_INSTALL_DIR/RAGPILOT_HOME happen to share a default today, but
# are independent overrides, so this is computed the same way rather than
# assumed equal to InstallDir above.
$RagpilotHome = if ($env:RAGPILOT_HOME) { $env:RAGPILOT_HOME } else { Join-Path $env:LOCALAPPDATA "RAGpilot" }

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
# Built side-by-side as "$VenvDir.new" rather than deleted-and-recreated in
# place: `ragpilot update install` re-runs this exact script from inside
# the currently-running $VenvDir\Scripts\ragpilot.exe. On Windows, deleting
# or overwriting that file while its own process is executing fails with a
# sharing violation ("[WinError 32] ... being used by another process"),
# which pip hits partway through installing into a venv rebuilt in place.
# Building fresh at a different path sidesteps the running files entirely;
# only the final swap below touches $VenvDir itself, and a directory rename
# (unlike an in-place delete/overwrite) succeeds even while a file inside it
# is open. Stale left-behind directories from an interrupted previous run
# are cleaned up first -- safe, since nothing still has them open.
$VenvDirNew = "$VenvDir.new"
$VenvDirOld = "$VenvDir.old"
if (Test-Path $VenvDirOld) { Remove-Item -Recurse -Force $VenvDirOld -ErrorAction SilentlyContinue }
if (Test-Path $VenvDirNew) { Remove-Item -Recurse -Force $VenvDirNew -ErrorAction SilentlyContinue }
& $Python.Exe @($Python.Args) -m venv $VenvDirNew

$VenvPython = Join-Path $VenvDirNew "Scripts\python.exe"
Write-Host "Installing RAGpilot (this downloads its dependencies, including torch -- may take a few minutes)..."
& $VenvPython -m pip install --quiet --upgrade pip
# Purge pip's cache before the real install: an entry written by whatever
# pip version was previously on this machine can fail to deserialize under
# the version just upgraded to above ("WARNING: Cache entry deserialization
# failed, entry ignored") -- pip already degrades safely from that (just
# re-downloads), but starting from a clean cache means it shouldn't happen
# at all. A cache that doesn't exist yet, or isn't writable, is not a
# reason to abort the install.
try { & $VenvPython -m pip cache purge *> $null } catch {}
# Still explained below in case some other/newer cache mismatch shows up
# despite the purge above: harmless either way, pip just re-downloads that
# entry instead of using a stale cache.
Write-Host "(you may see `"Cache entry deserialization failed`" warnings below -- harmless, pip just re-downloads that entry)"
# Deliberately not --quiet here: pip's normal download/build progress output
# is the only feedback during a multi-minute, multi-hundred-MB install (torch
# chief among the dependencies) -- silencing it makes a slow-but-working
# install indistinguishable from a hung one.
& $VenvPython -m pip install $AppDir

# Swap the new venv into place. If something (e.g. the very process running
# this script, during a self-upgrade) still has a file in $VenvDir open, the
# rename to $VenvDirOld leaves it in place under a different name rather
# than failing outright -- it becomes unlocked and gets swept up by the
# cleanup at the top of the next install/upgrade run.
if (Test-Path $VenvDir) { Rename-Item -Path $VenvDir -NewName (Split-Path $VenvDirOld -Leaf) }
Rename-Item -Path $VenvDirNew -NewName (Split-Path $VenvDir -Leaf)
Remove-Item -Recurse -Force $VenvDirOld -ErrorAction SilentlyContinue

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


# Lets `ragpilot update install` (update/installer.py) detect that this is
# an install-script install and where to re-run this same script, rather
# than guessing from the running interpreter's own path -- see this
# file's own record of itself as the one thing that can't guess itself.
New-Item -ItemType Directory -Force -Path $RagpilotHome | Out-Null
$InstallInfo = [ordered]@{
    install_method = "install-script"
    repository     = $Repo
    install_dir    = $InstallDir
    venv_dir       = $VenvDir
    bin_dir        = $BinDir
}
$InstallInfo | ConvertTo-Json | Set-Content -Path (Join-Path $RagpilotHome "install_info.json") -Encoding UTF8

Write-Host ""
Write-Host "Run 'ragpilot version' to verify, then 'ragpilot init' to get started."
