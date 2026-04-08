#!/bin/bash
# Kindle Capture ビルド & コード署名スクリプト
#
# 使い方:
#   ./build.sh          # ビルド + 署名
#   ./build.sh --setup  # 初回: 自己署名証明書を作成（1回だけ実行）
#
# 自己署名証明書で一貫した identity を使うことで、
# アップデート後も画面収録・アクセシビリティの権限が維持される。
set -e

APP_NAME="Kindle Capture"
BUNDLE_ID="com.local.kindlecapture"
CERT_NAME="KindleCapture Dev"
APP_PATH="dist/${APP_NAME}.app"

# ── 証明書セットアップ（初回のみ） ──
if [ "$1" = "--setup" ]; then
    echo "=== 自己署名コード署名証明書を作成 ==="

    # 既に存在するか確認
    if security find-identity -v -p codesigning | grep -q "$CERT_NAME"; then
        echo "証明書 '${CERT_NAME}' は既に存在します。"
        security find-identity -v -p codesigning | grep "$CERT_NAME"
        exit 0
    fi

    TMPDIR_CERT=$(mktemp -d)
    KEY_FILE="${TMPDIR_CERT}/cert.key"
    CERT_FILE="${TMPDIR_CERT}/cert.pem"
    P12_FILE="${TMPDIR_CERT}/cert.p12"

    echo "秘密鍵を生成中..."
    openssl genrsa -out "$KEY_FILE" 2048 2>/dev/null

    echo "自己署名証明書を生成中..."
    openssl req -new -x509 -key "$KEY_FILE" -out "$CERT_FILE" \
        -days 3650 -subj "/CN=${CERT_NAME}" \
        -addext "keyUsage=digitalSignature" \
        -addext "extendedKeyUsage=codeSigning" \
        2>/dev/null

    echo "PKCS12 に変換中..."
    openssl pkcs12 -export -inkey "$KEY_FILE" -in "$CERT_FILE" \
        -out "$P12_FILE" -passout pass:temppass123 -legacy 2>/dev/null || \
    openssl pkcs12 -export -inkey "$KEY_FILE" -in "$CERT_FILE" \
        -out "$P12_FILE" -passout pass:temppass123 2>/dev/null

    echo "キーチェーンにインポート中..."
    security import "$P12_FILE" -k ~/Library/Keychains/login.keychain-db \
        -T /usr/bin/codesign -P "temppass123" -A

    echo "証明書を信頼設定中..."
    security add-trusted-cert -d -r trustRoot \
        -k ~/Library/Keychains/login.keychain-db "$CERT_FILE" 2>/dev/null || {
        echo ""
        echo "⚠ 自動信頼設定に失敗しました（管理者パスワードが必要な場合があります）。"
        echo "  手動で信頼設定を行ってください:"
        echo "  1. キーチェーンアクセスを開く"
        echo "  2. 「ログイン」キーチェーン → 「証明書」カテゴリ"
        echo "  3. 「${CERT_NAME}」をダブルクリック"
        echo "  4. 「信頼」を展開 → 「コード署名」を「常に信頼」に変更"
    }

    # 後片付け
    rm -rf "$TMPDIR_CERT"

    echo ""
    echo "=== 確認 ==="
    if security find-identity -v -p codesigning | grep -q "$CERT_NAME"; then
        security find-identity -v -p codesigning | grep "$CERT_NAME"
        echo ""
        echo "証明書 '${CERT_NAME}' を作成しました。"
        echo "以降は ./build.sh でビルドすれば自動署名されます。"
    else
        echo "⚠ 証明書がコード署名用として認識されていません。"
        echo "  キーチェーンアクセスで信頼設定を確認してください。"
    fi
    exit 0
fi

# ── ビルド ──
echo "=== py2app ビルド ==="
rm -rf build dist
.venv/bin/python setup.py py2app

if [ ! -d "$APP_PATH" ]; then
    echo "エラー: ビルドに失敗しました。"
    exit 1
fi

# ── コード署名 ──
# 証明書の存在確認
if security find-identity -v -p codesigning | grep -q "$CERT_NAME"; then
    echo ""
    echo "=== コード署名 (${CERT_NAME}) ==="

    # py2app が install_name_tool でバイナリを書き換えた後、__LINKEDIT が壊れて
    # 署名できないファイルがある。壊れたものは元ファイルから復元してから再署名する。
    echo "破損バイナリを修復中..."
    find "$APP_PATH" -type f \( -name "*.so" -o -name "*.dylib" \) | while read -r f; do
        # 署名除去を試み、失敗したら元ファイルから復元
        if ! codesign --remove-signature "$f" 2>/dev/null; then
            BASENAME=$(basename "$f")
            # .venv から元ファイルを検索
            ORIG=$(find .venv -name "$BASENAME" -type f 2>/dev/null | head -1)
            if [ -n "$ORIG" ]; then
                echo "  復元: $BASENAME"
                rm -f "$f"
                cp "$ORIG" "$f"
                # rpath を修正
                RPATH="@executable_path/../Frameworks/$BASENAME"
                install_name_tool -id "$RPATH" "$f" 2>/dev/null || true
                codesign --remove-signature "$f" 2>/dev/null || true
            fi
        fi
    done

    # Python フレームワーク本体
    find "$APP_PATH/Contents/Frameworks" -name "Python" -path "*/Versions/*/Python" | while read -r f; do
        codesign --remove-signature "$f" 2>/dev/null || true
    done

    # メイン実行ファイル
    codesign --remove-signature "$APP_PATH/Contents/MacOS/Kindle Capture" 2>/dev/null || true

    # 全サブコンポーネントを署名（深い階層から）
    echo "サブコンポーネントを署名中..."
    find "$APP_PATH" -type f \( -name "*.so" -o -name "*.dylib" \) | while read -r f; do
        if ! codesign --force --sign "$CERT_NAME" "$f" 2>/dev/null; then
            echo "  ⚠ 署名失敗: $(basename "$f")"
        fi
    done

    # Python フレームワーク本体を署名
    find "$APP_PATH/Contents/Frameworks" -name "Python" -path "*/Versions/*/Python" | while read -r f; do
        codesign --force --sign "$CERT_NAME" "$f" 2>/dev/null || true
    done

    # アプリバンドル全体を署名
    echo "アプリバンドルを署名中..."
    codesign --force --sign "$CERT_NAME" \
        --identifier "$BUNDLE_ID" \
        "$APP_PATH"

    echo ""
    echo "=== 署名確認 ==="
    codesign -dvvv "$APP_PATH" 2>&1 | grep -E "Identifier|Signature|TeamIdentifier|Authority"
    echo ""
    codesign --verify "$APP_PATH" 2>&1 && echo "署名検証: OK" || echo "署名検証: ⚠ 検証に問題あり"
else
    echo ""
    echo "⚠ 証明書 '${CERT_NAME}' が見つかりません。ad-hoc 署名のままです。"
    echo "  初回は ./build.sh --setup を実行して証明書を作成してください。"
    echo "  (ad-hoc 署名ではアップデートのたびに権限の再許可が必要です)"
fi

echo ""
echo "=== ビルド完了 ==="
echo "アプリ: ${APP_PATH}"
du -sh "$APP_PATH"
