#!/usr/bin/env bash
# PyGBSentry update: git pull + refresh dependencies + sync database
set -e
cd "$(dirname "$0")"
echo "[1/3] git pull ..."
git pull
cd backend
if [ -d venv ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
echo "[2/3] Refreshing dependencies ..."
pip install -q -r requirements.txt
echo "[3/3] Syncing database ..."
python app/initial_data.py
echo ""
echo "[ OK ] Update done. Run ./start.sh (run ./stop.sh first if it is running)."
