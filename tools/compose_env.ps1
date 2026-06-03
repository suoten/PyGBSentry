param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("up", "down", "ps", "logs")]
  [string]$Action,
  [Parameter(Mandatory = $true)]
  [ValidateSet("dev", "prod")]
  [string]$Env,
  [string]$Service = "",
  [int]$Tail = 200,
  [switch]$Follow
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Action -eq "up") {
  python tools/env_manager.py switch --env $Env
  python tools/env_manager.py validate --env $Env
  docker compose --profile $Env up -d
}
elseif ($Action -eq "down") {
  docker compose --profile $Env down
}
elseif ($Action -eq "ps") {
  docker compose --profile $Env ps
}
else {
  $logArgs = @("compose", "--profile", $Env, "logs")
  if ($Follow) {
    $logArgs += "-f"
  }
  $logArgs += @("--tail", $Tail)
  if ([string]::IsNullOrWhiteSpace($Service)) {
    docker @logArgs
  }
  else {
    docker @($logArgs + $Service)
  }
}
