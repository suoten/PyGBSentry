#!/usr/bin/env bash
# PyGBSentry stop: kills backend (and SIP listener if any)
cd "$(dirname "$0")/backend"
[ -f .env ] || { echo "[INFO] .env not found - nothing to stop."; exit 0; }
PORT=$(grep -E '^BACKEND_PUBLIC_PORT=' .env | head -1 | cut -d= -f2)
PORT=${PORT:-8000}
SIP_PORT=$(grep -E '^SIP_PORT=' .env | head -1 | cut -d= -f2)
SIP_PORT=${SIP_PORT:-5062}

KILLED=0
for P in $(ss -tlnp 2>/dev/null | grep -E ":($PORT|$SIP_PORT) " | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
  kill "$P" 2>/dev/null && KILLED=1
done
sleep 1
if [ "$KILLED" = "1" ]; then echo "[ OK ] PyGBSentry stopped."; else echo "[INFO] PyGBSentry was not running."; fi
