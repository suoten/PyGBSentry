param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("switch", "validate")]
  [string]$Action,
  [Parameter(Mandatory = $true)]
  [ValidateSet("dev", "prod")]
  [string]$Env
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python tools/env_manager.py $Action --env $Env
