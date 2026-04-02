#!/usr/bin/env python3
"""
Kindle スクショ → PDF デスクトップアプリ

Kindle アプリのウィンドウをキャプチャし、自動ページ送りで
全ページのスクリーンショットを撮り、1つのPDFにまとめる。

起動:
    .venv/bin/python kindle_capture_app.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import Quartz
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPixmap, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ── Kindle 操作関数 ──────────────────────────────────────────────


def find_kindle_window():
    """Kindle アプリのウィンドウ ID を取得する。見つからなければ None を返す。"""
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    candidates = []
    for win in window_list:
        owner = win.get("kCGWindowOwnerName", "")
        layer = win.get("kCGWindowLayer", 999)
        bounds = win.get("kCGWindowBounds", {})
        w = bounds.get("Width", 0)
        h = bounds.get("Height", 0)
        if owner == "Kindle" and layer == 0 and w > 100 and h > 100:
            candidates.append(
                {
                    "id": win["kCGWindowNumber"],
                    "name": win.get("kCGWindowName", ""),
                    "width": w,
                    "height": h,
                }
            )
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["width"] * c["height"])


def activate_kindle():
    subprocess.run(
        ["osascript", "-e", 'tell application "Kindle" to activate'],
        check=True,
    )
    time.sleep(0.5)


def send_key(direction: str):
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
    subprocess.run(
        ["screencapture", "-x", "-o", f"-l{window_id}", output_path],
        check=True,
    )


def pngs_to_pdf(png_dir: Path, output_pdf: Path):
    png_files = sorted(png_dir.glob("p*.png"))
    if not png_files:
        return 0
    images = []
    for f in png_files:
        img = Image.open(f).convert("RGB")
        images.append(img)
    first = images[0]
    first.save(output_pdf, save_all=True, append_images=images[1:], resolution=150)
    return len(images)


# ── ワーカースレッド ─────────────────────────────────────────────


class CaptureWorker(QThread):
    """バックグラウンドでキャプチャを実行するスレッド"""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(str)  # 結果メッセージ
    error = pyqtSignal(str)
    preview = pyqtSignal(str)  # プレビュー用 PNG パス

    def __init__(self, pages, start, direction, delay, out_dir, output_pdf):
        super().__init__()
        self.pages = pages
        self.start = start
        self.direction = direction
        self.delay = delay
        self.out_dir = Path(out_dir)
        self.output_pdf = Path(output_pdf)
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)

            win = find_kindle_window()
            if win is None:
                self.error.emit("Kindle のウィンドウが見つかりません。\nKindle を起動して本を開いてください。")
                return

            window_id = win["id"]
            self.progress.emit(0, 0, f"Kindle 検出: {win['width']}x{win['height']} \"{win['name']}\"")

            activate_kindle()
            time.sleep(2)

            total = self.pages - self.start + 1

            for i in range(self.start, self.pages + 1):
                if self._stop_requested:
                    self.progress.emit(0, 0, "中断しました")
                    self.finished.emit(f"中断しました（{i - self.start} ページキャプチャ済み）")
                    return

                page_num = i - self.start + 1
                filename = f"p{i:04d}.png"
                filepath = self.out_dir / filename

                self.progress.emit(page_num, total, f"キャプチャ中: {filename}")
                capture_window(window_id, str(filepath))
                self.preview.emit(str(filepath))

                if i < self.pages:
                    send_key(self.direction)
                    time.sleep(self.delay)

            self.progress.emit(total, total, "PDF 変換中...")
            count = pngs_to_pdf(self.out_dir, self.output_pdf)

            if count == 0:
                self.error.emit("PNG ファイルが見つかりません。")
            else:
                self.finished.emit(f"完了! {count} ページ → {self.output_pdf.name}")

        except Exception as e:
            self.error.emit(str(e))


# ── メインウィンドウ ─────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Kindle Capture")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── タイトル ──
        title = QLabel("Kindle スクショ → PDF")
        title.setFont(QFont(".AppleSystemUIFont", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # ── 設定グループ ──
        settings_group = QGroupBox("設定")
        settings_layout = QVBoxLayout(settings_group)

        # ページ数
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("総ページ数:"))
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 9999)
        self.spin_pages.setValue(100)
        row1.addWidget(self.spin_pages)
        row1.addWidget(QLabel("開始ページ:"))
        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, 9999)
        self.spin_start.setValue(1)
        row1.addWidget(self.spin_start)
        settings_layout.addLayout(row1)

        # 方向 & ディレイ
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("ページ送り:"))
        self.combo_direction = QComboBox()
        self.combo_direction.addItems(["→ 右 (right)", "← 左 (left)"])
        row2.addWidget(self.combo_direction)
        row2.addWidget(QLabel("待ち時間:"))
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.1, 10.0)
        self.spin_delay.setValue(1.0)
        self.spin_delay.setSuffix(" 秒")
        self.spin_delay.setSingleStep(0.1)
        row2.addWidget(self.spin_delay)
        settings_layout.addLayout(row2)

        # 出力先
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("保存先:"))
        self.label_outdir = QLabel(str(Path.home() / "Desktop"))
        self.label_outdir.setStyleSheet("color: #555;")
        row3.addWidget(self.label_outdir, 1)
        btn_browse = QPushButton("変更...")
        btn_browse.clicked.connect(self.browse_output)
        row3.addWidget(btn_browse)
        settings_layout.addLayout(row3)

        layout.addWidget(settings_group)

        # ── Kindle 状態 ──
        status_group = QGroupBox("Kindle 状態")
        status_layout = QHBoxLayout(status_group)
        self.label_kindle = QLabel("未検出")
        self.label_kindle.setStyleSheet("color: #999;")
        status_layout.addWidget(self.label_kindle, 1)
        btn_detect = QPushButton("検出")
        btn_detect.clicked.connect(self.detect_kindle)
        status_layout.addWidget(btn_detect)
        layout.addWidget(status_group)

        # ── プレビュー ──
        self.label_preview = QLabel()
        self.label_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_preview.setMinimumHeight(120)
        self.label_preview.setStyleSheet(
            "background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 4px;"
        )
        self.label_preview.setText("プレビュー")
        layout.addWidget(self.label_preview, 1)

        # ── プログレスバー ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.label_status = QLabel("準備完了")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label_status)

        # ── ボタン ──
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ キャプチャ開始")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.Bold))
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #007AFF; color: white; border-radius: 8px; }"
            "QPushButton:hover { background-color: #005EC4; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self.btn_start.clicked.connect(self.start_capture)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setFixedHeight(40)
        self.btn_stop.setFont(QFont(".AppleSystemUIFont", 14))
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #FF3B30; color: white; border-radius: 8px; }"
            "QPushButton:hover { background-color: #D32F2F; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_capture)
        btn_layout.addWidget(self.btn_stop)

        layout.addLayout(btn_layout)

        # 初回検出
        self.detect_kindle()

    def browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "保存先を選択", self.label_outdir.text())
        if d:
            self.label_outdir.setText(d)

    def detect_kindle(self):
        win = find_kindle_window()
        if win:
            self.label_kindle.setText(
                f"検出済み: {win['width']}x{win['height']}  \"{win['name']}\""
            )
            self.label_kindle.setStyleSheet("color: #34C759;")
        else:
            self.label_kindle.setText("未検出 — Kindle を起動して本を開いてください")
            self.label_kindle.setStyleSheet("color: #FF3B30;")

    def start_capture(self):
        pages = self.spin_pages.value()
        start = self.spin_start.value()
        direction = "right" if self.combo_direction.currentIndex() == 0 else "left"
        delay = self.spin_delay.value()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = Path(self.label_outdir.text()) / f"kindle_capture_{timestamp}"
        output_pdf = out_dir / f"kindle_{timestamp}.pdf"

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setMaximum(pages - start + 1)
        self.progress_bar.setValue(0)

        self.worker = CaptureWorker(pages, start, direction, delay, out_dir, output_pdf)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.preview.connect(self.on_preview)
        self.worker.start()

    def stop_capture(self):
        if self.worker:
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.label_status.setText("停止中...")

    def on_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.label_status.setText(message)

    def on_preview(self, path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.label_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.label_preview.setPixmap(scaled)

    def on_finished(self, message):
        self.label_status.setText(message)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.worker = None

        if "完了" in message:
            QMessageBox.information(self, "完了", message)

    def on_error(self, message):
        self.label_status.setText("エラー")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.worker = None
        QMessageBox.critical(self, "エラー", message)


# ── エントリポイント ──


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kindle Capture")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
