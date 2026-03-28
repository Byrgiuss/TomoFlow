#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication


def convert_html_to_pdf(html_path: Path, pdf_path: Path, timeout_sec: int = 300) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop()
    page = QWebEnginePage()

    state = {
        "done": False,
        "error": None,
    }

    def _finish_error(msg: str) -> None:
        if state["done"]:
            return
        state["done"] = True
        state["error"] = msg
        loop.quit()

    def _finish_ok() -> None:
        if state["done"]:
            return
        state["done"] = True
        loop.quit()

    def _on_pdf_finished(file_path: str, success: bool) -> None:
        if not success:
            _finish_error(f"PDF print failed: {file_path}")
            return
        _finish_ok()

    def _on_load_finished(success: bool) -> None:
        if not success:
            _finish_error("Failed to load HTML in WebEngine.")
            return
        page.printToPdf(str(pdf_path))

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: _finish_error(f"Timed out after {timeout_sec} seconds."))
    timer.start(timeout_sec * 1000)

    page.pdfPrintingFinished.connect(_on_pdf_finished)
    page.loadFinished.connect(_on_load_finished)
    page.load(QUrl.fromLocalFile(str(html_path.resolve())))

    loop.exec()
    timer.stop()

    if state["error"]:
        raise RuntimeError(state["error"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a local HTML file to PDF using Qt WebEngine.")
    parser.add_argument("--input", required=True, type=Path, help="Input HTML file path")
    parser.add_argument("--output", required=True, type=Path, help="Output PDF file path")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input HTML not found: {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    convert_html_to_pdf(args.input, args.output, timeout_sec=args.timeout)
    print(f"PDF saved: {args.output}")


if __name__ == "__main__":
    main()
