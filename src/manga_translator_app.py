#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import threading

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from translate_chapter_single_html import (
    NO_SECOND_LANGUAGE,
    SUPPORTED_LANGUAGES,
    SUPPORTED_MODELS,
    translate_chapter_to_single_html,
)

APP_NAME = "TomoFlow"
APP_SETTINGS_ORG = "FurkanAkman"
APP_SETTINGS_NAME = "MangaTranslatorApp"
APP_LOGO_FILE = "TomoFlowLogo.png"


def _resource_path(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        base / filename,
        base / "assets" / filename,
        Path(__file__).resolve().parent.parent / "assets" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


class TranslationWorker(QObject):
    progress = Signal(str, int, int, str, bool)
    done = Signal(str, int, int, bool, int)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        input_dir: Path,
        output_path: Path,
        output_format: str,
        model: str,
        api_key: str,
        lang1: str,
        lang2: str,
    ) -> None:
        super().__init__()
        self.input_dir = input_dir
        self.output_path = output_path
        self.output_format = output_format
        self.model = model
        self.api_key = api_key
        self.lang1 = lang1
        self.lang2 = lang2
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            saved_path, total_pages, failures, cancelled, processed_pages = translate_chapter_to_single_html(
                input_dir=self.input_dir,
                output_path=self.output_path,
                model=self.model,
                api_key=self.api_key,
                primary_language=self.lang1,
                second_language=self.lang2,
                progress_callback=self._on_progress,
                cancel_requested=self._cancel_event.is_set,
                output_format=self.output_format,
            )
            self.done.emit(str(saved_path), total_pages, failures, cancelled, processed_pages)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _on_progress(self, stage: str, index: int, total: int, message: str, success: bool) -> None:
        self.progress.emit(stage, index, total, message, success)


class MangaTranslatorWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        logo_path = _resource_path(APP_LOGO_FILE)
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
        self.setFixedSize(860, 390)
        self.settings = QSettings(APP_SETTINGS_ORG, APP_SETTINGS_NAME)

        self.thread: QThread | None = None
        self.worker: TranslationWorker | None = None

        self._build_ui()
        self._load_saved_api_key()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.editingFinished.connect(self._persist_api_key)
        self.output_html_radio = QRadioButton("HTML")
        self.output_pdf_radio = QRadioButton("PDF")
        self.output_html_radio.setChecked(True)
        self.output_html_radio.toggled.connect(self._on_output_format_changed)
        self.output_pdf_radio.toggled.connect(self._on_output_format_changed)

        self.model_combo = QComboBox()
        self.model_combo.addItems(SUPPORTED_MODELS)
        self.model_combo.setCurrentText("gpt-4.1")

        self.lang1_combo = QComboBox()
        self.lang1_combo.addItems(SUPPORTED_LANGUAGES)
        self.lang1_combo.setCurrentText("English")

        self.lang2_combo = QComboBox()
        self.lang2_combo.addItems([NO_SECOND_LANGUAGE] + SUPPORTED_LANGUAGES)
        self.lang2_combo.setCurrentText(NO_SECOND_LANGUAGE)

        browse_input_btn = QPushButton("Browse")
        browse_input_btn.clicked.connect(self._browse_input)

        browse_output_btn = QPushButton("Browse")
        browse_output_btn.clicked.connect(self._browse_output)
        self.clear_api_key_btn = QPushButton("Clear Key")
        self.clear_api_key_btn.clicked.connect(self._clear_api_key)

        grid.addWidget(QLabel("Input Folder"), 0, 0)
        grid.addWidget(self.input_edit, 0, 1)
        grid.addWidget(browse_input_btn, 0, 2)

        grid.addWidget(QLabel("Output Path"), 1, 0)
        grid.addWidget(self.output_edit, 1, 1)
        grid.addWidget(browse_output_btn, 1, 2)

        format_row = QHBoxLayout()
        format_row.addWidget(self.output_html_radio)
        format_row.addWidget(self.output_pdf_radio)
        format_row.addStretch(1)
        grid.addWidget(QLabel("Output Format"), 2, 0)
        grid.addLayout(format_row, 2, 1, 1, 2)

        grid.addWidget(QLabel("OpenAI API Key"), 3, 0)
        grid.addWidget(self.api_key_edit, 3, 1)
        grid.addWidget(self.clear_api_key_btn, 3, 2)

        grid.addWidget(QLabel("Model"), 4, 0)
        grid.addWidget(self.model_combo, 4, 1)

        grid.addWidget(QLabel("Language 1 (Required)"), 5, 0)
        grid.addWidget(self.lang1_combo, 5, 1)

        grid.addWidget(QLabel("Language 2 (Optional)"), 6, 0)
        grid.addWidget(self.lang2_combo, 6, 1)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.clicked.connect(self._start_translation)
        self.cancel_btn = QPushButton("Cancel Translation")
        self.cancel_btn.clicked.connect(self._cancel_translation)
        self.cancel_btn.setEnabled(False)
        self.help_btn = QPushButton("Help")
        self.help_btn.clicked.connect(self._show_help)
        self.about_btn = QPushButton("About")
        self.about_btn.clicked.connect(self._show_about)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.cancel_btn)
        controls.addStretch(1)
        controls.addWidget(self.help_btn)
        controls.addWidget(self.about_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self.status_label = QLabel("Ready")

        root.addLayout(grid)
        root.addLayout(controls)
        root.addWidget(self.progress)
        root.addWidget(self.status_label)

    def _set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.input_edit.setEnabled(not running)
        self.output_edit.setEnabled(not running)
        self.api_key_edit.setEnabled(not running)
        self.clear_api_key_btn.setEnabled(not running)
        self.output_html_radio.setEnabled(not running)
        self.output_pdf_radio.setEnabled(not running)
        self.model_combo.setEnabled(not running)
        self.lang1_combo.setEnabled(not running)
        self.lang2_combo.setEnabled(not running)

    def _load_saved_api_key(self) -> None:
        saved = str(self.settings.value("api_key", "", type=str) or "").strip()
        if saved:
            self.api_key_edit.setText(saved)

    def _persist_api_key(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if api_key:
            self.settings.setValue("api_key", api_key)
        else:
            self.settings.remove("api_key")
        self.settings.sync()

    @Slot()
    def _clear_api_key(self) -> None:
        self.api_key_edit.clear()
        self.settings.remove("api_key")
        self.settings.sync()

    @Slot()
    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Help")
        dialog.resize(760, 560)
        model_list = ", ".join(SUPPORTED_MODELS)

        layout = QVBoxLayout(dialog)
        text = QTextEdit(dialog)
        text.setReadOnly(True)
        text.setPlainText(
            f"{APP_NAME} - Help\n\n"
            "What does this program do?\n"
            "- Reads manga pages (PNG/JPG/WEBP) from the selected folder and sends them to the chosen OpenAI model in sequence.\n"
            "- Extracts Japanese text panel by panel.\n"
            "- Preserves manga reading order (right-to-left, top-to-bottom).\n"
            "- Translates text into selected output languages.\n"
            "- Builds one standalone output file where each page image is shown on the left and panel translations are shown on the right.\n\n"
            "How does it work?\n"
            "1) Images in the input folder are sorted naturally (1,2,3...10).\n"
            "2) Each page is sent to the API one by one.\n"
            "3) Results are parsed panel-by-panel and mapped to selected translation languages.\n"
            "4) Progress bar and status text are updated during processing.\n"
            "5) At the end, a single output file is generated in selected format (HTML or PDF).\n\n"
            "Fields and buttons\n"
            "- Input Folder: Chapter folder that contains page images.\n"
            "- Output Path: Full path of the resulting output file.\n"
            "- Output Format: Choose HTML or PDF.\n"
            "- OpenAI API Key: Your OpenAI key (masked). Saved locally for future sessions.\n"
            "- Clear Key: Removes the saved API key and clears the field.\n"
            f"- Model: Model selection ({model_list}).\n"
            "- Language 1 (Required): Primary translation language (required).\n"
            "- Language 2 (Optional): Secondary translation language (optional, can be (None)).\n"
            "- Start Translation: Starts the translation process.\n"
            "- Cancel Translation: Requests cancellation. If confirmed, pages translated so far are saved as partial HTML.\n"
            "- Help: Opens this help window.\n"
            "- About: Opens application information.\n\n"
            "Cancellation behavior\n"
            "- When cancellation is requested, the app stops after the current API request finishes.\n"
            "- Already translated pages are not lost; partial output is written in selected format.\n\n"
            "Error behavior\n"
            "- If API key is missing/invalid or connection issues happen, affected pages may be recorded with error info.\n"
            "- Completion popup shows success, partial success, or error details."
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(text)
        layout.addWidget(buttons)
        dialog.exec()

    @Slot()
    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About")
        dialog.resize(430, 330)
        layout = QVBoxLayout(dialog)

        logo_label = QLabel(dialog)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = _resource_path(APP_LOGO_FILE)
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            if not pixmap.isNull():
                logo_label.setPixmap(
                    pixmap.scaled(
                        180,
                        180,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        layout.addWidget(logo_label)

        label = QLabel(
            f"<h2>{APP_NAME}</h2>"
            "<p>Created by Byrgiuss in 2026.</p>"
            '<p><a href="https://github.com/Byrgiuss/">https://github.com/Byrgiuss/</a></p>',
            dialog,
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    @Slot()
    def _cancel_translation(self) -> None:
        if self.worker is None:
            return
        answer = QMessageBox.question(
            self,
            "Cancel Translation",
            "Translation will be interrupted and only pages translated so far will be saved. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.worker.request_cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancel requested. Stopping after current request...")

    @Slot()
    def _browse_input(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select Chapter Folder")
        if not selected:
            return
        self.input_edit.setText(selected)
        if not self.output_edit.text().strip():
            ext = ".pdf" if self._selected_output_format() == "pdf" else ".html"
            self.output_edit.setText(str(Path(selected) / f"chapter_translation{ext}"))

    @Slot()
    def _browse_output(self) -> None:
        output_format = self._selected_output_format()
        ext = ".pdf" if output_format == "pdf" else ".html"
        file_filter = "PDF files (*.pdf);;All files (*)" if output_format == "pdf" else "HTML files (*.html);;All files (*)"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output File",
            str(Path.cwd() / f"chapter_translation{ext}"),
            file_filter,
        )
        if selected:
            self.output_edit.setText(selected)

    @Slot()
    def _on_output_format_changed(self) -> None:
        current = self.output_edit.text().strip()
        if not current:
            return
        path = Path(current)
        desired = ".pdf" if self._selected_output_format() == "pdf" else ".html"
        if path.suffix.lower() in {".html", ".pdf"} and path.suffix.lower() != desired:
            self.output_edit.setText(str(path.with_suffix(desired)))

    def _selected_output_format(self) -> str:
        return "pdf" if self.output_pdf_radio.isChecked() else "html"

    @Slot()
    def _start_translation(self) -> None:
        input_str = self.input_edit.text().strip()
        output_str = self.output_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        lang1 = self.lang1_combo.currentText().strip()
        lang2 = self.lang2_combo.currentText().strip()
        output_format = self._selected_output_format()

        if not input_str:
            QMessageBox.critical(self, "Validation Error", "Input folder path is required.")
            return
        if not output_str:
            QMessageBox.critical(self, "Validation Error", "Output path is required.")
            return
        if not api_key:
            QMessageBox.critical(self, "Validation Error", "API key is required.")
            return
        if not lang1:
            QMessageBox.critical(self, "Validation Error", "Language 1 is required.")
            return
        if model not in SUPPORTED_MODELS:
            QMessageBox.critical(self, "Validation Error", "Please select a valid model.")
            return
        self._persist_api_key()

        input_dir = Path(input_str).expanduser()
        if not input_dir.exists() or not input_dir.is_dir():
            QMessageBox.critical(self, "Validation Error", "Input folder path is invalid.")
            return

        output_path = Path(output_str).expanduser()
        desired_suffix = ".pdf" if output_format == "pdf" else ".html"
        if output_path.suffix.lower() != desired_suffix:
            output_path = output_path.with_suffix(desired_suffix)
            self.output_edit.setText(str(output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label.setText("Starting...")
        self._set_running(True)

        self.thread = QThread(self)
        self.worker = TranslationWorker(
            input_dir=input_dir,
            output_path=output_path,
            output_format=output_format,
            model=model,
            api_key=api_key,
            lang1=lang1,
            lang2=lang2,
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)

        self.thread.start()

    @Slot()
    def _on_thread_finished(self) -> None:
        self.worker = None
        self.thread = None

    @Slot(str, int, int, str, bool)
    def _on_progress(self, stage: str, index: int, total: int, message: str, success: bool) -> None:
        if stage == "total":
            max_pages = max(total, 1)
            self.progress.setRange(0, max_pages)
            self.progress.setValue(0)
            self.status_label.setText(f"Detected {total} page(s).")
        elif stage == "page_start":
            self.status_label.setText(f"Translating {index}/{total}: {message}")
        elif stage == "page_done":
            self.progress.setValue(index)
            prefix = "OK" if success else "FAIL"
            self.status_label.setText(f"{prefix} {index}/{total}: {message}")
        elif stage == "finished":
            self.progress.setValue(self.progress.maximum())
            self.status_label.setText(f"Done. Output: {message}")
        elif stage == "cancelled":
            self.progress.setValue(index)
            self.status_label.setText(f"Cancelled at {index}/{total}. Partial output: {message}")

    @Slot(str, int, int, bool, int)
    def _on_done(
        self,
        saved_path: str,
        total_pages: int,
        failures: int,
        cancelled: bool,
        processed_pages: int,
    ) -> None:
        self._set_running(False)
        if cancelled:
            QMessageBox.information(
                self,
                "Cancelled",
                (
                    "Translation cancelled by user.\n\n"
                    f"Processed pages: {processed_pages}/{total_pages}\n"
                    f"Failed pages: {failures}\n"
                    f"Partial output saved to:\n{saved_path}"
                ),
            )
        elif failures == 0:
            QMessageBox.information(
                self,
                "Completed",
                f"Translation finished successfully.\n\nPages: {total_pages}\nOutput: {saved_path}",
            )
        else:
            QMessageBox.warning(
                self,
                "Completed With Errors",
                f"Finished with {failures} failed page(s).\n\nPages: {total_pages}\nOutput: {saved_path}",
            )

    @Slot(str)
    def _on_error(self, error_text: str) -> None:
        self._set_running(False)
        self.status_label.setText("Error.")
        QMessageBox.critical(self, "Error", error_text)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._persist_api_key()
        super().closeEvent(event)


def main() -> None:
    app = QApplication([])
    logo_path = _resource_path(APP_LOGO_FILE)
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))
    window = MangaTranslatorWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
