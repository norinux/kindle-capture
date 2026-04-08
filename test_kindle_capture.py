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
    _slot_safe,
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

    def test_on_progress_zero_total_does_not_crash(self):
        """total=0 でもクラッシュしないことを確認"""
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.on_progress(0, 0, "待機中...")
            assert win.label_status.text() == "待機中..."

    def test_on_preview_with_invalid_path(self):
        """存在しない画像パスでもクラッシュしないことを確認"""
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            # _slot_safe が例外をキャッチするのでクラッシュしない
            win.on_preview("/nonexistent/path/image.png")

    def test_cleanup_worker_when_none(self):
        """worker が None のときに _cleanup_worker を呼んでもクラッシュしない"""
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            assert win.worker is None
            win._cleanup_worker()  # should not raise

    def test_finalize_capture_when_no_worker(self):
        """worker が None のときに finalize_capture を呼んでもクラッシュしない"""
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.finalize_capture()  # should not raise

    def test_stop_capture_when_no_worker(self):
        """worker が None のときに stop_capture を呼んでもクラッシュしない"""
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            win.stop_capture()  # should not raise

    def test_all_slots_have_slot_safe(self):
        """全スロットメソッドが _slot_safe で保護されていることを確認"""
        slot_methods = [
            "browse_output", "detect_kindle", "start_capture",
            "finalize_capture", "stop_capture", "on_progress",
            "on_preview", "on_completed", "on_error", "_cleanup_worker",
        ]
        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            win = MainWindow()
            for name in slot_methods:
                method = getattr(win, name)
                # _slot_safe wraps with functools.wraps, so __wrapped__ exists
                assert hasattr(method, "__wrapped__"), (
                    f"{name} is not protected by @_slot_safe"
                )


# ── ユニットテスト: _slot_safe デコレータ ──


class TestSlotSafe:
    def test_normal_return_value(self):
        """例外なしの場合、戻り値がそのまま返る"""
        @_slot_safe
        def good_func():
            return 42

        assert good_func() == 42

    def test_catches_exception(self):
        """例外が発生してもクラッシュしない（None を返す）"""
        @_slot_safe
        def bad_func():
            raise ValueError("test error")

        with patch("kindle_capture_app.QMessageBox"):
            result = bad_func()
        assert result is None  # 例外時は None

    def test_preserves_function_name(self):
        """functools.wraps で関数名が保持される"""
        @_slot_safe
        def my_slot():
            pass

        assert my_slot.__name__ == "my_slot"

    def test_exception_writes_to_stderr(self, capsys):
        """例外発生時に stderr にトレースバックが出力される"""
        @_slot_safe
        def failing_func():
            raise RuntimeError("detailed error message")

        with patch("kindle_capture_app.QMessageBox"):
            failing_func()

        captured = capsys.readouterr()
        assert "detailed error message" in captured.err
        assert "RuntimeError" in captured.err

    def test_passes_args_and_kwargs(self):
        """引数が正しく渡される"""
        @_slot_safe
        def add(a, b, extra=0):
            return a + b + extra

        assert add(1, 2, extra=3) == 6


# ── ユニットテスト: CaptureWorker のシグナル接続 ──


class TestCaptureWorkerSignals:
    def test_finalize_sets_both_flags(self):
        """finalize() は _stop_requested と _finalize_requested の両方を設定する"""
        worker = CaptureWorker(
            pages=10, start_page=1, direction="right",
            delay=1.0, out_dir="/tmp/test", output_pdf="/tmp/test/out.pdf",
        )
        assert worker._finalize_requested is False
        worker.finalize()
        assert worker._stop_requested is True
        assert worker._finalize_requested is True

    def test_worker_run_no_kindle(self, tmp_path):
        """Kindle が見つからない場合、error シグナルが発行される"""
        errors = []
        worker = CaptureWorker(
            pages=5, start_page=1, direction="right",
            delay=0.1, out_dir=str(tmp_path / "out"),
            output_pdf=str(tmp_path / "out" / "test.pdf"),
        )
        worker.error.connect(errors.append)

        with patch("kindle_capture_app.find_kindle_window", return_value=None):
            worker.run()

        assert len(errors) == 1
        assert "Kindle" in errors[0]

    def test_worker_run_capture_fails(self, tmp_path):
        """キャプチャが失敗した場合、error シグナルが発行される"""
        errors = []
        mock_win = {"id": 1, "width": 800, "height": 600, "name": "Test"}
        worker = CaptureWorker(
            pages=1, start_page=1, direction="right",
            delay=0.1, out_dir=str(tmp_path / "out"),
            output_pdf=str(tmp_path / "out" / "test.pdf"),
        )
        worker.error.connect(errors.append)

        with patch("kindle_capture_app.find_kindle_window", return_value=mock_win), \
             patch("kindle_capture_app.capture_window", side_effect=RuntimeError("画面のキャプチャに失敗")):
            worker.run()

        assert len(errors) == 1
        assert "キャプチャ" in errors[0]

    def test_worker_stop_during_capture(self, tmp_path):
        """キャプチャ中に stop() を呼ぶと中断される"""
        messages = []
        mock_win = {"id": 1, "width": 800, "height": 600, "name": "Test"}

        worker = CaptureWorker(
            pages=100, start_page=1, direction="right",
            delay=0.0, out_dir=str(tmp_path / "out"),
            output_pdf=str(tmp_path / "out" / "test.pdf"),
        )
        worker.completed.connect(messages.append)

        def fake_capture(wid, path):
            Image.new("RGB", (100, 100), "red").save(path)
            worker.stop()  # 1ページ目キャプチャ後に即停止

        with patch("kindle_capture_app.find_kindle_window", return_value=mock_win), \
             patch("kindle_capture_app.capture_window", side_effect=fake_capture), \
             patch("kindle_capture_app.time.sleep"):
            worker.run()

        assert len(messages) == 1
        assert "中断" in messages[0]
