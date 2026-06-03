#!/usr/bin/env bash
# 从 https://github.com/FFmpeg/FFmpeg 克隆源码并编译安装到固定前缀（默认 /usr/local/ffmpeg）。
#
# 用法（源码编译建议 root 或 sudo）:
#   bash scripts/install_ffmpeg_from_source.sh
#   PREFIX=/opt/ffmpeg bash scripts/install_ffmpeg_from_source.sh
#   TRY_PACKAGE_FIRST=0 bash scripts/install_ffmpeg_from_source.sh    # 跳过 dnf/apt，直接源码编译
#   AUTO_INSTALL_BUILD_DEPS=1 sudo bash scripts/install_ffmpeg_from_source.sh
#
# 环境变量:
#   TRY_PACKAGE_FIRST   默认 1：若为 root，先尝试 dnf/yum/apt/apk 安装 ffmpeg（快得多）
#   AUTO_INSTALL_BUILD_DEPS 默认 0：若为 1 且为 root，在安装源码前自动安装 git/gcc/make/nasm 等
#   PREFIX              默认 /usr/local/ffmpeg
#   FFMPEG_REPO         默认 https://github.com/FFmpeg/FFmpeg.git
#   SHALLOW             默认 1：浅克隆
#   BUILD_DIR           默认 /tmp/ffmpeg-build-$$
#
# 说明:
# - 仅 git clone 不会生成 ffmpeg，必须 configure + make + install。
# - 源码编译耗时较长；有发行版包时优先包管理器。
# - 上游: https://github.com/FFmpeg/FFmpeg

set -euo pipefail

FFMPEG_REPO="${FFMPEG_REPO:-https://github.com/FFmpeg/FFmpeg.git}"
PREFIX="${PREFIX:-/usr/local/ffmpeg}"
BUILD_DIR="${BUILD_DIR:-/tmp/ffmpeg-build-$$}"
SHALLOW="${SHALLOW:-1}"
TRY_PACKAGE_FIRST="${TRY_PACKAGE_FIRST:-1}"
AUTO_INSTALL_BUILD_DEPS="${AUTO_INSTALL_BUILD_DEPS:-0}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    exit 1
  }
}

is_root() {
  [[ "$(id -u)" == "0" ]]
}

try_install_ffmpeg_package() {
  [[ "$TRY_PACKAGE_FIRST" == "1" ]] || return 1
  is_root || return 1
  echo "==> 尝试通过包管理器安装 ffmpeg (TRY_PACKAGE_FIRST=1)..."
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y ffmpeg
  elif command -v yum >/dev/null 2>&1; then
    yum install -y ffmpeg
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache ffmpeg
  elif command -v zypper >/dev/null 2>&1; then
    zypper install -y ffmpeg
  else
    echo "未识别包管理器，跳过包安装。" >&2
    return 1
  fi
  command -v ffmpeg >/dev/null 2>&1
}

install_build_dependencies() {
  [[ "$AUTO_INSTALL_BUILD_DEPS" == "1" ]] || return 0
  is_root || {
    echo "AUTO_INSTALL_BUILD_DEPS=1 需要 root/sudo。" >&2
    exit 1
  }
  echo "==> 安装源码编译依赖 (AUTO_INSTALL_BUILD_DEPS=1)..."
  if command -v apt-get >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
      git build-essential nasm yasm pkg-config zlib1g-dev
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git gcc gcc-c++ make nasm yasm pkg-config zlib-devel
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git gcc gcc-c++ make nasm yasm pkgconfig zlib-devel
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache git build-base nasm yasm pkgconf zlib-dev
  elif command -v zypper >/dev/null 2>&1; then
    zypper install -y git gcc gcc-c++ make nasm yasm pkg-config zlib-devel
  else
    echo "未识别包管理器，请手工安装: git, gcc, make, nasm, pkg-config, zlib 开发包" >&2
    exit 1
  fi
}

if command -v ffmpeg >/dev/null 2>&1; then
  echo "已存在 ffmpeg: $(command -v ffmpeg)"
  ffmpeg -version | head -n 1
  exit 0
fi

if try_install_ffmpeg_package; then
  echo "已通过包管理器安装。"
  ffmpeg -version | head -n 1
  exit 0
fi

install_build_dependencies

need_cmd git
if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
  echo "缺少 C 编译器 (cc 或 gcc)。可设置 AUTO_INSTALL_BUILD_DEPS=1 并由 root 执行。" >&2
  exit 1
fi
need_cmd make

if ! command -v nasm >/dev/null 2>&1; then
  echo "建议安装 nasm（x86_64 上 FFmpeg 常用）。可设置 AUTO_INSTALL_BUILD_DEPS=1 或由 root 安装 nasm。" >&2
fi

mkdir -p "$BUILD_DIR"
cleanup() { rm -rf "$BUILD_DIR"; }
trap cleanup EXIT

echo "==> 克隆 FFmpeg 到 $BUILD_DIR/src"
if [[ "$SHALLOW" == "1" ]]; then
  git clone --depth 1 "$FFMPEG_REPO" "$BUILD_DIR/src"
else
  git clone "$FFMPEG_REPO" "$BUILD_DIR/src"
fi

cd "$BUILD_DIR/src"

echo "==> configure (prefix=$PREFIX)"
./configure \
  --prefix="$PREFIX" \
  --enable-shared \
  --disable-static \
  --disable-debug \
  --disable-doc \
  --disable-ffplay

echo "==> make -j$(nproc 2>/dev/null || echo 4)"
make -j"$(nproc 2>/dev/null || echo 4)"

echo "==> make install"
make install

echo
echo "安装完成: $PREFIX/bin/ffmpeg"
"$PREFIX/bin/ffmpeg" -version | head -n 1
echo
echo "请将下列路径加入运行 ZLM / 后端的 PATH（或写入 /etc/profile.d/ffmpeg.sh）:"
echo "  export PATH=\"$PREFIX/bin:\$PATH\""
