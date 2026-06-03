#!/usr/bin/env bash
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_INSTALL_BUILD_DEPS="${AUTO_INSTALL_BUILD_DEPS:-1}" \
TRY_PACKAGE_FIRST="${TRY_PACKAGE_FIRST:-1}" \
bash "$dir/install_ffmpeg_from_source.sh"
