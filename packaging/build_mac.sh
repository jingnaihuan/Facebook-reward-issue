#!/usr/bin/env bash
# 在 Mac 上构建 RewardHub.app。从仓库根目录运行：bash packaging/build_mac.sh
# 用独立 venv 隔离构建，避免本机 anaconda/全局环境污染（如 numpy/tensorflow 冲突）导致 PyInstaller 扫描崩溃。
set -e
cd "$(dirname "$0")/.."

VENV="${REWARD_BUILD_VENV:-.build_venv}"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install pyinstaller playwright openpyxl

# 不需要 chromium 内核（运行时驱动系统 Chrome），故不执行 playwright install chromium。
rm -rf build dist
"$VENV/bin/python" -m PyInstaller packaging/reward_hub.spec --noconfirm

echo "完成：dist/RewardHub.app"
# 打成 zip：把 .app 与「首次打开必读.txt」放进同一文件夹一起分发
rm -rf "dist/RewardHub-mac"
mkdir -p "dist/RewardHub-mac"
cp -R "dist/RewardHub.app" "dist/RewardHub-mac/"
cp "packaging/首次打开必读.txt" "dist/RewardHub-mac/"
( cd dist && ditto -c -k --sequesterRsrc --keepParent "RewardHub-mac" "RewardHub-mac.zip" )
echo "分发包：dist/RewardHub-mac.zip"
