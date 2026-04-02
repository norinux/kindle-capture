"""
Kindle Capture アプリのテスト

実行:
    .venv/bin/python -m pytest test_kindle_capture.py -v
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# テスト用 QApplication（PyQt6 テストに必須）
app = QApplication.instance() or QApplication(sys.argv)

from kindle_capture_app import (
    CaptureWorker,
    MainWindow,
    find_kindle_window,
    images_are_same,
    pngs_to_pdf,
)


# ── ユニットテスト: images_are_same ──


class TestImagesAreSame:
    def test_identical_images(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="red")
        img.save(tmp_path / "a.png")
        img.save(tmp_path / "b.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "b.png")) is True

    def test_different_images(self, tmp_path):
        Image.new("RGB", (100, 100), color="red").save(tmp_path / "a.png")
        Image.new("RGB", (100, 100), color="blue").save(tmp_path / "b.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "b.png")) is False

    def test_different_sizes(self, tmp_path):
        Image.new("RGB", (100, 100), color="red").save(tmp_path / "a.png")
        Image.new("RGB", (200, 200), color="red").save(tmp_path / "b.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "b.png")) is False

    def test_nearly_identical_images_above_threshold(self, tmp_path):
        """1ピクセルだけ異なる画像は同一とみなされる"""
        img_a = Image.new("RGB", (100, 100), color=(128, 128, 128))
        img_a.save(tmp_path / "a.png")
        img_b = img_a.copy()
        img_b.putpixel((50, 50), (255, 0, 0))
        img_b.save(tmp_path / "b.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "b.png")) is True

    def test_nonexistent_file(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="red")
        img.save(tmp_path / "a.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "nope.png")) is False

    def test_custom_threshold(self, tmp_path):
        """threshold=1.0 だと完全一致のみ True"""
        img_a = Image.new("RGB", (100, 100), color=(128, 128, 128))
        img_a.save(tmp_path / "a.png")
        img_b = img_a.copy()
        img_b.putpixel((50, 50), (255, 0, 0))
        img_b.save(tmp_path / "b.png")
        assert images_are_same(str(tmp_path / "a.png"), str(tmp_path / "b.png"), threshold=1.0) is False


# ── ユニットテスト: pngs_to_pdf ──


class TestPngsToPdf:
    def test_empty_directory(self, tmp_path):
        output_pdf = tmp_path / "out.pdf"
        count = pngs_to_pdf(tmp_path, output_pdf)
        assert count == 0
        assert not output_pdf.exists()

    def test_single_page(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="red")
        img.save(tmp_path / "p0001.png")
        output_pdf = tmp_path / "out.pdf"

        count = pngs_to_pdf(tmp_path, output_pdf)
        assert count == 1
        assert output_pdf.exists()
        assert output_pdf.stat().st_size > 0

    def test_multiple_pages(self, tmp_path):
        for i in range(1, 4):
            img = Image.new("RGB", (200, 300), color=(i * 80, 0, 0))
            img.save(tmp_path / f"p{i:04d}.png")
        output_pdf = tmp_path / "out.pdf"

        count = pngs_to_pdf(tmp_path, output_pdf)
        assert count == 3
        assert output_pdf.exists()

    def test_ignores_non_matching_files(self, tmp_path):
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(tmp_path / "p0001.png")
        img.save(tmp_path / "other.png")
        img.save(tmp_path / "screenshot.png")
        output_pdf = tmp_path / "out.pdf"

        count = pngs_to_pdf(tmp_path, output_pdf)
        assert count == 1

    def test_page_order(self, tmp_path):
        """ページ番号順にソートされることを確認"""
        for i in [3, 1, 2]:
            img = Image.new("RGB", (100, 100), color=(i * 80, 0, 0))
            img.save(tmp_path / f"p{i:04d}.png")
        output_pdf = tmp_path / "out.pdf"

        count = pngs_to_pdf(tmp_path, output_pdf)
        assert count == 3


# ── ユニットテスト: find_kindle_window ──


class TestFindKindleWindow:
    @patch("kindle_capture_app.Quartz")
    def test_no_kindle_window(self, mock_quartz):
        mock_quartz.CGWindowListCopyWindowInfo.return_value = []
        mock_quartz.kCGWindowListOptionOnScreenOnly = 1
        mock_quartz.kCGWindowListExcludeDesktopElements = 2
        mock_quartz.kCGNullWindowID = 0
        result = find_kindle_window()
        assert result is None

    @patch("kindle_capture_app.Quartz")
    def test_finds_kindle_window(self, mock_quartz):
        mock_quartz.kCGWindowListOptionOnScreenOnly = 1
        mock_quartz.kCGWindowListExcludeDesktopElements = 2
        mock_quartz.kCGNullWindowID = 0
        mock_quartz.CGWindowListCopyWindowInfo.return_value = [
            {
                "kCGWindowOwnerName": "Kindle",
                "kCGWindowName": "My Book",
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 42,
                "kCGWindowBounds": {"Width": 800, "Height": 600},
            }
        ]
        result = find_kindle_window()
        assert result is not None
        assert result["id"] == 42
        assert result["width"] == 800
        assert result["height"] == 600

    @patch("kindle_capture_app.Quartz")
    def test_selects_largest_window(self, mock_quartz):
        mock_quartz.kCGWindowListOptionOnScreenOnly = 1
        mock_quartz.kCGWindowListExcludeDesktopElements = 2
        mock_quartz.kCGNullWindowID = 0
        mock_quartz.CGWindowListCopyWindowInfo.return_value = [
            {
                "kCGWindowOwnerName": "Kindle",
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 10,
                "kCGWindowBounds": {"Width": 200, "Height": 200},
            },
            {
                "kCGWindowOwnerName": "Kindle",
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 20,
                "kCGWindowBounds": {"Width": 1200, "Height": 800},
            },
        ]
        result = find_kindle_window()
        assert result["id"] == 20

    @patch("kindle_capture_app.Quartz")
    def test_ignores_small_windows(self, mock_quartz):
        mock_quartz.kCGWindowListOptionOnScreenOnly = 1
        mock_quartz.kCGWindowListExcludeDesktopElements = 2
        mock_quartz.kCGNullWindowID = 0
        mock_quartz.CGWindowListCopyWindowInfo.return_value = [
            {
                "kCGWindowOwnerName": "Kindle",
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 5,
                "kCGWindowBounds": {"Width": 50, "Height": 50},
            },
        ]
        result = find_kindle_window()
        assert result is None

    @patch("kindle_capture_app.Quartz")
    def test_ignores_non_kindle_windows(self, mock_quartz):
        mock_quartz.kCGWindowListOptionOnScreenOnly = 1
        mock_quartz.kCGWindowListExcludeDesktopElements = 2
        mock_quartz.kCGNullWindowID = 0
        mock_quartz.CGWindowListCopyWindowInfo.return_value = [
            {
                "kCGWindowOwnerName": "Safari",
                "kCGWindowLayer": 0,
                "kCGWindowNumber": 99,
                "kCGWindowBounds": {"Width": 800, "Height": 600},
            },
        ]
        result = find_kindle_window()
        assert result is None


# ── ユニットテスト: CaptureWorker ──


class TestCaptureWorker:
    def test_does_not_shadow_qthread_start(self):
        """self.start が QThread.start() を上書きしないことを確認"""
        worker = CaptureWorker(
            pages=10,
            start_page=1,
            direction="right",
            delay=1.0,
            out_dir="/tmp/test",
            output_pdf="/tmp/test/out.pdf",
        )
        assert callable(worker.start), "worker.start() must be callable (QThread.start)"
        assert worker.start_page == 1
        assert worker.pages == 10

    def test_stop_flag(self):
        worker = CaptureWorker(
            pages=5,
            start_page=1,
            direction="right",
            delay=0.1,
            out_dir="/tmp/test",
            output_pdf="/tmp/test/out.pdf",
        )
        assert worker._stop_requested is False
        worker.stop()
        assert worker._stop_requested is True

    def test_attributes(self):
        worker = CaptureWorker(
            pages=50,
            start_page=5,
            direction="left",
            delay=2.0,
            out_dir="/tmp/capture",
            output_pdf="/tmp/capture/book.pdf",
        )
        assert worker.pages == 50
        assert worker.start_page == 5
        assert worker.direction == "left"
        assert worker.delay == 2.0
        assert worker.out_dir == Path("/tmp/capture")
        assert worker.output_pdf == Path("/tmp/capture/book.pdf")


# ── ユニットテスト: MainWindow ──


class TestMainWindow:
    def test_window_creation(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            assert win.windowTitle() == "Kindle Capture"
            assert win.worker is None

    def test_initial_values(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            assert win.spin_pages.value() == 100
            assert win.spin_start.value() == 1
            assert win.spin_delay.value() == 1.0
            assert win.btn_start.isEnabled()
            assert not win.btn_stop.isEnabled()

    def test_detect_kindle_not_found(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            assert "未検出" in win.label_kindle.text()

    def test_detect_kindle_found(self):
        mock_win = {"id": 1, "width": 800, "height": 600, "name": "Test Book"}
        with patch("kindle_capture_app.find_kindle_window", return_value=mock_win):
            win = MainWindow()
            assert "検出済み" in win.label_kindle.text()
            assert "800x600" in win.label_kindle.text()

    def test_detect_kindle_handles_exception(self):
        with patch("kindle_capture_app.find_kindle_window", side_effect=RuntimeError("test")):
            win = MainWindow()
            assert "検出エラー" in win.label_kindle.text()

    def test_on_completed_resets_buttons(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.btn_start.setEnabled(False)
            win.btn_stop.setEnabled(True)
            with patch.object(win, "worker", None):
                win.on_completed("中断しました")
            assert win.btn_start.isEnabled()
            assert not win.btn_stop.isEnabled()

    def test_on_error_resets_buttons(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.btn_start.setEnabled(False)
            win.btn_stop.setEnabled(True)
            with patch("kindle_capture_app.QMessageBox"):
                win.on_error("テストエラー")
            assert win.btn_start.isEnabled()
            assert not win.btn_stop.isEnabled()

    def test_on_progress_updates_bar(self):
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.on_progress(5, 10, "キャプチャ中")
            assert win.progress_bar.value() == 5
            assert win.progress_bar.maximum() == 10
            assert win.label_status.text() == "キャプチャ中"
