$ErrorActionPreference = 'Stop'
$appRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $appRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is required to build the bundled workflow engine.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js and npm are required to build the desktop application.' }

Write-Host 'Locking and syncing the Windows build dependencies...'
uv lock
uv sync --locked --extra dev --extra browser --extra desktop --extra credentials
if ($LASTEXITCODE -ne 0) { throw 'uv dependency sync failed.' }

$resourceDir = Join-Path $appRoot 'src-tauri\resources'
$workDir = Join-Path $appRoot '.build\pyinstaller'
New-Item -ItemType Directory -Force -Path $resourceDir, $workDir | Out-Null
Write-Host 'Freezing the Python workflow bridge into a self-contained executable...'
uv run --locked --extra browser --extra desktop --extra credentials pyinstaller `
  --noconfirm --clean --onefile --name openrpa-bridge `
  --distpath $resourceDir --workpath $workDir --specpath $workDir `
  --paths $appRoot --collect-submodules openrpa --collect-all regex `
  --collect-all playwright --collect-all pyautogui --collect-all pywinauto --collect-all comtypes --collect-all keyring `
  (Join-Path $appRoot 'scripts\bridge_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed to create the bundled workflow engine.' }
$bridgePath = Join-Path $resourceDir 'openrpa-bridge.exe'
if (-not (Test-Path $bridgePath)) { throw 'The frozen workflow engine executable is missing.' }

Write-Host 'Building the Windows NSIS installer...'
$tauri = Join-Path $appRoot 'node_modules\.bin\tauri.cmd'
if (-not (Test-Path $tauri)) { throw 'Run npm ci before building the Windows installer.' }
& $tauri build --bundles nsis
if ($LASTEXITCODE -ne 0) { throw 'Tauri failed to build the NSIS installer.' }

$version = (Get-Content (Join-Path $appRoot 'package.json') -Raw | ConvertFrom-Json).version
$installer = Get-ChildItem (Join-Path $appRoot 'src-tauri\target\release\bundle\nsis') -Filter "*$version*x64-setup.exe" | Select-Object -First 1
if (-not $installer) { throw 'Tauri reported success but no NSIS setup executable was produced.' }
$releaseDir = Join-Path $appRoot 'release'
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$versionedInstaller = Join-Path $releaseDir "Open-RPA-Studio-Setup-$version-x64.exe"
Copy-Item -LiteralPath $installer.FullName -Destination $versionedInstaller -Force
Write-Host "Installer created: $versionedInstaller"
certutil.exe -hashfile $versionedInstaller SHA256
if ($LASTEXITCODE -ne 0) { throw 'Could not calculate the installer SHA-256.' }
