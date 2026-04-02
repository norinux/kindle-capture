#!/bin/bash
# Kindle Capture DMG インストーラー作成スクリプト
set -e

APP_NAME="Kindle Capture"
DMG_NAME="KindleCapture"
VERSION="1.0.0"
APP_PATH="dist/${APP_NAME}.app"
DMG_DIR="dist/dmg"
DMG_OUTPUT="dist/${DMG_NAME}-${VERSION}.dmg"

if [ ! -d "$APP_PATH" ]; then
    echo "エラー: ${APP_PATH} が見つかりません。先に py2app でビルドしてください。"
    exit 1
fi

echo "=== DMG 作成中 ==="

# 作業ディレクトリ準備
rm -rf "$DMG_DIR" "$DMG_OUTPUT"
mkdir -p "$DMG_DIR"

# .app をコピー
cp -R "$APP_PATH" "$DMG_DIR/"

# Applications へのシンボリックリンク
ln -s /Applications "$DMG_DIR/Applications"

# DMG 作成
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$DMG_DIR" \
    -ov -format UDZO \
    "$DMG_OUTPUT"

# 後片付け
rm -rf "$DMG_DIR"

echo ""
echo "=== 完了 ==="
echo "DMG: $DMG_OUTPUT"
du -sh "$DMG_OUTPUT"
