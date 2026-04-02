#!/usr/bin/env python3
"""
Kindle スクショ → PDF 変換ツール

Kindle アプリのウィンドウを指定してスクリーンショットを撮り、
自動ページ送りで全ページをキャプチャし、1つのPDFにまとめる。

使い方:
    .venv/bin/python kindle_capture.py --pages 327
    .venv/bin/python kindle_capture.py --pages 327 --start 1 --direction right --delay 1.0
    .venv/bin/python kindle_capture.py --pages 327 --output mybook.pdf
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import Quartz
from PIL import Image


def find_kindle_window():
    """Kindle アプリのウィンドウ ID (CGWindowID) を取得する"""
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    candidates = []
    for win in window_list:
        owner = win.get("kCGWindowOwnerName", "")
        name = win.get("kCGWindowName", "")
        layer = win.get("kCGWindowLayer", 999)
        bounds = win.get("kCGWindowBounds", {})
        w = bounds.get("Width", 0)
        h = bounds.get("Height", 0)
        if owner == "Kindle" and layer == 0 and w > 100 and h > 100:
            candidates.append({
                "id": win["kCGWindowNumber"],
                "name": name,
                "width": w,
                "height": h,
            })

    if not candidates:
        print("エラー: Kindle のウィンドウが見つかりません。Kindle を起動して本を開いてください。")
        sys.exit(1)

    # 一番大きいウィンドウを選ぶ（本文ウィンドウのはず）
    best = max(candidates, key=lambda c: c["width"] * c["height"])
    print(f"Kindle ウィンドウ検出: ID={best['id']}  "
          f"{best['width']}x{best['height']}  \"{best['name']}\"")
    return best["id"]


def activate_kindle():
    """Kindle を最前面にする"""
    subprocess.run(
        ["osascript", "-e", 'tell application "Kindle" to activate'],
        check=True,
    )
    time.sleep(0.5)


def click_kindle_center():
    """Kindle ウィンドウの中央をクリックしてフォーカスを確保する"""
    script = '''
    tell application "System Events"
        tell process "Kindle"
            set frontmost to true
            try
                set winFrame to frame of front window
                set midX to ((item 1 of winFrame) + (item 3 of winFrame) / 2) as integer
                set midY to ((item 2 of winFrame) + (item 4 of winFrame) / 2) as integer
                click at {midX, midY}
            end try
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True)


def send_key(direction: str):
    """ウィンドウ中央クリック後にページ送りキーを送信する"""
    # key code: 123=左矢印, 124=右矢印
    key_code = 124 if direction == "right" else 123
    script = f'''
    tell application "System Events"
        tell process "Kindle"
            set frontmost to true
            try
                set winFrame to frame of front window
                set midX to ((item 1 of winFrame) + (item 3 of winFrame) / 2) as integer
                set midY to ((item 2 of winFrame) + (item 4 of winFrame) / 2) as integer
                click at {{midX, midY}}
            end try
            key code {key_code}
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True)


def capture_window(window_id: int, output_path: str):
    """指定ウィンドウのスクリーンショットを撮る"""
    subprocess.run(
        ["screencapture", "-x", "-o", f"-l{window_id}", output_path],
        check=True,
    )


def pngs_to_pdf(png_dir: Path, output_pdf: Path):
    """PNG ファイルを1つの PDF にまとめる"""
    png_files = sorted(png_dir.glob("p*.png"))
    if not png_files:
        print("エラー: PNG ファイルが見つかりません。")
        sys.exit(1)

    images = []
    for f in png_files:
        img = Image.open(f).convert("RGB")
        images.append(img)

    first = images[0]
    first.save(output_pdf, save_all=True, append_images=images[1:], resolution=150)
    print(f"\nPDF 作成完了: {output_pdf}  ({len(images)} ページ)")


def main():
    parser = argparse.ArgumentParser(description="Kindle スクショ → PDF 変換ツール")
    parser.add_argument("--pages", type=int, required=True, help="総ページ数")
    parser.add_argument("--start", type=int, default=1, help="開始ページ番号 (default: 1)")
    parser.add_argument("--direction", choices=["left", "right"], default="right",
                        help="ページ送り方向 (default: right)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="ページ送り後の待ち秒数 (default: 1.0)")
    parser.add_argument("--output", type=str, default=None,
                        help="出力 PDF ファイル名 (default: kindle_YYYYMMDD_HHMMSS.pdf)")
    parser.add_argument("--outdir", type=str, default=None,
                        help="PNG 保存先ディレクトリ (default: ~/Desktop/kindle_capture)")
    parser.add_argument("--no-shadow", action="store_true",
                        help="ウィンドウの影を含めない (-o フラグ、デフォルトで有効)")
    args = parser.parse_args()

    # 出力ディレクトリ
    if args.outdir:
        out_dir = Path(args.outdir)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = Path.home() / "Desktop" / f"kindle_capture_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 出力 PDF
    if args.output:
        output_pdf = Path(args.output)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_pdf = out_dir / f"kindle_{timestamp}.pdf"

    print("=== Kindle スクショ → PDF ===")
    print(f"  ページ数:   {args.pages}  (開始: {args.start})")
    print(f"  ページ送り: {'→ 右' if args.direction == 'right' else '← 左'}")
    print(f"  待ち時間:   {args.delay} 秒")
    print(f"  PNG 保存先: {out_dir.resolve()}")
    print(f"  PDF 出力先: {output_pdf.resolve()}")
    print()

    # Kindle ウィンドウ検出
    window_id = find_kindle_window()

    # Kindle を前面に
    activate_kindle()

    print(f"\n3秒後にキャプチャを開始します... Kindle の画面を触らないでください。")
    time.sleep(3)

    # ページキャプチャループ
    total = args.pages - args.start + 1
    for i in range(args.start, args.pages + 1):
        page_num = i - args.start + 1
        filename = f"p{i:04d}.png"
        filepath = out_dir / filename

        print(f"\r  [{page_num}/{total}] {filename}", end="", flush=True)

        capture_window(window_id, str(filepath))

        # 最後のページではページ送りしない
        if i < args.pages:
            send_key(args.direction)
            time.sleep(args.delay)

    print(f"\n\nスクリーンショット完了: {total} ページ")

    # PDF 変換
    print("\nPDF に変換中...")
    pngs_to_pdf(out_dir, output_pdf)


if __name__ == "__main__":
    main()
