# 构建开源版绿色包（Windows PowerShell 5.1+）：backend + frontend/dist + run.sh + run.bat，产出 zip。
# 用法（在 editions/open-source 目录下）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-green-package.ps1 -Version 1.0.0
param(
  [string]$Version = "1.0.0",
  [string]$Suffix = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Fail([string]$Msg) {
  Write-Error $Msg
  exit 1
}

function Need-Cmd([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Fail "缺少依赖命令：$Name。请先安装后重试。"
  }
}

Need-Cmd "node"
Need-Cmd "npm"
Need-Cmd "python"

# Sanity check: required docs/tools must exist
if (-not (Test-Path (Join-Path $root "docs\\PREBUILT.md"))) { Fail "缺少 docs\\PREBUILT.md（绿色包说明）" }
if (-not (Test-Path (Join-Path $root "docs\\RUNTIME_QUERY_CHEATSHEET.md"))) { Fail "缺少 docs\\RUNTIME_QUERY_CHEATSHEET.md（运维速查表）" }
if (-not (Test-Path (Join-Path $root "tools\\query_runtime_events.py"))) { Fail "缺少 tools\\query_runtime_events.py（运维查询脚本）" }

Write-Host "==> Verify runtime plugin coverage..."
python (Join-Path $root "tools\\check_runtime_coverage.py")
if ($LASTEXITCODE -ne 0) { Fail "runtime 覆盖率自检失败（tools\\check_runtime_coverage.py）" }

$outName = if ([string]::IsNullOrWhiteSpace($Suffix)) { "PyGBSentry-oss-$Version" } else { "PyGBSentry-oss-$Version-$Suffix" }
$tmpDir = Join-Path $root "dist-green"
$stageDir = Join-Path $tmpDir $outName
$archive = Join-Path $root "$outName.zip"

Write-Host "==> Building frontend..."
Set-Location (Join-Path $root "frontend")
if (Test-Path ".\package-lock.json") {
  npm ci
} else {
  npm install
}
if ($LASTEXITCODE -ne 0) { Fail "前端依赖安装失败（npm）。" }
npm run build
if ($LASTEXITCODE -ne 0) { Fail "前端构建失败（npm run build）。" }
Set-Location $root

Write-Host "==> Preparing green package in $stageDir..."
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

function Copy-FolderFiltered {
  param(
    [string]$SourceDir,
    [string]$DestDir
  )
  New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
  $all = Get-ChildItem -Path (Join-Path $SourceDir "*") -Recurse -Force -File
  $files = $all | Where-Object {
    $p = $_.FullName
    ($p -notmatch "\\venv\\") -and
    ($p -notmatch "\\__pycache__\\") -and
    ($p -notmatch "\.pyc$") -and
    ($p -notmatch "\\\.git\\") -and
    ($p -notmatch "\\\.env$")
  }
  foreach ($f in $files) {
    $rel = $f.FullName.Substring($SourceDir.Length).TrimStart("\","/")
    $target = Join-Path $DestDir $rel
    $parent = Split-Path $target -Parent
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    Copy-Item -Force -LiteralPath $f.FullName -Destination $target
  }
}

# backend（过滤 venv/__pycache__/.pyc/.env/.git）
Copy-FolderFiltered -SourceDir (Join-Path $root "backend") -DestDir (Join-Path $stageDir "backend")

# frontend dist
Copy-Item -Recurse -Force -Path (Join-Path $root "frontend\\dist") -Destination (Join-Path $stageDir "frontend-dist")

# run scripts & docs
Copy-Item -Force -Path (Join-Path $root "run.sh"), (Join-Path $root "run.bat"), (Join-Path $root "start-frontend.sh"), (Join-Path $root "start-frontend.bat") -Destination $stageDir
if (Test-Path (Join-Path $root "docs\\PREBUILT.md")) {
  Copy-Item -Force -Path (Join-Path $root "docs\\PREBUILT.md") -Destination $stageDir
}
if (Test-Path (Join-Path $root "docs\\RUNTIME_QUERY_CHEATSHEET.md")) {
  Copy-Item -Force -Path (Join-Path $root "docs\\RUNTIME_QUERY_CHEATSHEET.md") -Destination $stageDir
}
if (Test-Path (Join-Path $root "tools\\query_runtime_events.py")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $stageDir "tools") | Out-Null
  Copy-Item -Force -Path (Join-Path $root "tools\\query_runtime_events.py") -Destination (Join-Path $stageDir "tools")
}
if (Test-Path (Join-Path $root "tools\\check_runtime_coverage.py")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $stageDir "tools") | Out-Null
  Copy-Item -Force -Path (Join-Path $root "tools\\check_runtime_coverage.py") -Destination (Join-Path $stageDir "tools")
}

@"
PyGBSentry 开源版绿色包
======================
1. 本机需安装 Python 3.10+，数据库（如 PostgreSQL/SQLite）与 ZLMediaKit 需自行配置。
2. 启动后端：运行 run.sh（Linux/macOS）或 run.bat（Windows），将自动创建虚拟环境并安装依赖，默认 http://0.0.0.0:8000。
3. 启动前端静态服务：运行 start-frontend.sh（Linux/macOS）或 start-frontend.bat（Windows），默认端口 8080（可通过环境变量 PORT 覆盖）。
4. 如需使用 Nginx：将 frontend-dist 目录配置为静态服务根目录。
5. 详细说明见 PREBUILT.md；运维查询速查表见 RUNTIME_QUERY_CHEATSHEET.md。
"@ | Set-Content -Encoding UTF8 -Path (Join-Path $stageDir "README-绿色包.txt")

Write-Host "==> Creating $archive..."
if (Test-Path $archive) { Remove-Item $archive -Force }
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $archive -Force

Write-Host "==> Done: $archive"
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }

