"""
py2app セットアップ

ビルド:
    .venv/bin/python setup.py py2app
"""

from setuptools import setup

APP = ["kindle_capture_app.py"]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "plist": {
        "CFBundleName": "Kindle Capture",
        "CFBundleDisplayName": "Kindle Capture",
        "CFBundleIdentifier": "com.local.kindlecapture",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSAppleEventsUsageDescription": "Kindle のウィンドウ操作とページ送りのために必要です。",
        "NSScreenCaptureUsageDescription": "Kindle のスクリーンショットを撮るために必要です。",
    },
    "packages": ["PyQt6"],
    "includes": [
        "PIL",
        "PIL.PdfImagePlugin",
        "Quartz",
        "AppKit",
    ],
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
