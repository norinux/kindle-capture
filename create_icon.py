#!/usr/bin/env python3
"""Kindle Capture アプリ用アイコン生成スクリプト"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import subprocess

SIZE = 1024

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 背景: 角丸四角 (macOS 風)
margin = 40
r = 180
bg_rect = [margin, margin, SIZE - margin, SIZE - margin]
draw.rounded_rectangle(bg_rect, radius=r, fill=(30, 30, 30))

# 本のアイコン (中央やや上)
book_cx, book_cy = SIZE // 2, SIZE // 2 - 40
bw, bh = 340, 420  # 本の幅・高さ
spine_x = book_cx  # 背表紙の中心線

# 左ページ
draw.polygon(
    [
        (spine_x - bw // 2, book_cy - bh // 2 + 20),
        (spine_x - 10, book_cy - bh // 2),
        (spine_x - 10, book_cy + bh // 2),
        (spine_x - bw // 2, book_cy + bh // 2 - 20),
    ],
    fill=(245, 245, 240),
)

# 右ページ
draw.polygon(
    [
        (spine_x + bw // 2, book_cy - bh // 2 + 20),
        (spine_x + 10, book_cy - bh // 2),
        (spine_x + 10, book_cy + bh // 2),
        (spine_x + bw // 2, book_cy + bh // 2 - 20),
    ],
    fill=(235, 235, 228),
)

# 左ページのテキスト行
for i in range(7):
    y = book_cy - bh // 2 + 80 + i * 42
    x1 = spine_x - bw // 2 + 45
    x2 = spine_x - 30
    lw = 3 if i % 3 == 0 else 2
    draw.line([(x1, y), (x2, y)], fill=(180, 180, 175), width=lw)

# 右ページのテキスト行
for i in range(7):
    y = book_cy - bh // 2 + 80 + i * 42
    x1 = spine_x + 30
    x2 = spine_x + bw // 2 - 45
    lw = 3 if i % 3 == 0 else 2
    draw.line([(x1, y), (x2, y)], fill=(180, 180, 175), width=lw)

# カメラアイコン (右下)
cam_cx, cam_cy = SIZE // 2 + 180, SIZE // 2 + 220
cam_r = 110

# カメラ本体の背景円
draw.ellipse(
    [cam_cx - cam_r, cam_cy - cam_r, cam_cx + cam_r, cam_cy + cam_r],
    fill=(0, 122, 255),
)

# カメラボディ
cam_w, cam_h = 90, 62
draw.rounded_rectangle(
    [cam_cx - cam_w // 2, cam_cy - cam_h // 2 + 5, cam_cx + cam_w // 2, cam_cy + cam_h // 2 + 5],
    radius=10,
    fill=(255, 255, 255),
)

# レンズ
lens_r = 18
draw.ellipse(
    [cam_cx - lens_r, cam_cy - lens_r + 5, cam_cx + lens_r, cam_cy + lens_r + 5],
    fill=(0, 122, 255),
)
draw.ellipse(
    [cam_cx - lens_r + 5, cam_cy - lens_r + 10, cam_cx + lens_r - 5, cam_cy + lens_r],
    fill=(255, 255, 255),
)

# フラッシュ部分
draw.rounded_rectangle(
    [cam_cx - 20, cam_cy - cam_h // 2 - 8, cam_cx + 8, cam_cy - cam_h // 2 + 8],
    radius=4,
    fill=(255, 255, 255),
)

# PNG 保存
icon_dir = Path(__file__).parent
png_path = icon_dir / "icon.png"
img.save(png_path, "PNG")
print(f"PNG 保存: {png_path}")

# iconutil で .icns 生成
iconset_dir = icon_dir / "icon.iconset"
iconset_dir.mkdir(exist_ok=True)

sizes = [16, 32, 64, 128, 256, 512, 1024]
for s in sizes:
    resized = img.resize((s, s), Image.Resampling.LANCZOS)
    if s == 1024:
        resized.save(iconset_dir / "icon_512x512@2x.png")
    else:
        resized.save(iconset_dir / f"icon_{s}x{s}.png")
        if s * 2 <= 1024:
            resized2 = img.resize((s * 2, s * 2), Image.Resampling.LANCZOS)
            resized2.save(iconset_dir / f"icon_{s}x{s}@2x.png")

icns_path = icon_dir / "icon.icns"
subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)
print(f"ICNS 保存: {icns_path}")
