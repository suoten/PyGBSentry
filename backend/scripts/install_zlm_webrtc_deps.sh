#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" != "0" ]]; then
  echo "请用 root/sudo 执行" >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y build-essential cmake git pkg-config libssl-dev libsrtp2-dev
  exit 0
fi

if command -v dnf >/dev/null 2>&1; then
  dnf install -y gcc gcc-c++ make cmake git pkgconfig openssl-devel libsrtp-devel || true
  exit 0
fi

if command -v yum >/dev/null 2>&1; then
  yum install -y epel-release || true
  yum install -y gcc gcc-c++ make cmake git pkgconfig openssl-devel libsrtp-devel || true
  exit 0
fi

if command -v apk >/dev/null 2>&1; then
  apk add --no-cache build-base cmake git pkgconf openssl-dev libsrtp-dev || true
  exit 0
fi

if command -v zypper >/dev/null 2>&1; then
  zypper install -y gcc gcc-c++ make cmake git pkg-config libopenssl-devel libsrtp-devel || true
  exit 0
fi

echo "未识别包管理器，请手工安装：cmake、gcc/g++、openssl 开发包、libsrtp 开发包" >&2
exit 1
