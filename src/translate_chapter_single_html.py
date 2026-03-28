#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import html
import os
import re
from pathlib import Path
from typing import Any, Callable

from openai import APIConnectionError, BadRequestError, OpenAI, RateLimitError

from translate_single_page import PROMPT, _extract_json, _sorted_panels

FIXED_IMAGE_WIDTH_PX = 707
FIXED_IMAGE_HEIGHT_PX = 1024
NO_SECOND_LANGUAGE = "(None)"
SUPPORTED_MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5-mini",
    "gpt-5.4",
]
SUPPORTED_OUTPUT_FORMATS = ["html", "pdf"]
SUPPORTED_LANGUAGES = [
    "Afrikaans",
    "Albanian",
    "Amharic",
    "Arabic",
    "Armenian",
    "Azerbaijani",
    "Basque",
    "Belarusian",
    "Bengali",
    "Bosnian",
    "Bulgarian",
    "Catalan",
    "Chinese (Simplified)",
    "Chinese (Traditional)",
    "Croatian",
    "Czech",
    "Danish",
    "Dutch",
    "English",
    "Estonian",
    "Filipino",
    "Finnish",
    "French",
    "Galician",
    "Georgian",
    "German",
    "Greek",
    "Gujarati",
    "Haitian Creole",
    "Hebrew",
    "Hindi",
    "Hungarian",
    "Icelandic",
    "Indonesian",
    "Irish",
    "Italian",
    "Japanese",
    "Kannada",
    "Kazakh",
    "Khmer",
    "Korean",
    "Kurdish",
    "Lao",
    "Latvian",
    "Lithuanian",
    "Macedonian",
    "Malay",
    "Malayalam",
    "Maltese",
    "Marathi",
    "Mongolian",
    "Nepali",
    "Norwegian",
    "Persian",
    "Polish",
    "Portuguese",
    "Punjabi",
    "Romanian",
    "Russian",
    "Serbian",
    "Sinhala",
    "Slovak",
    "Slovenian",
    "Spanish",
    "Swahili",
    "Swedish",
    "Tamil",
    "Telugu",
    "Thai",
    "Turkish",
    "Ukrainian",
    "Urdu",
    "Uzbek",
    "Vietnamese",
    "Welsh",
    "Yoruba",
]
ProgressCallback = Callable[[str, int, int, str, bool], None]
CancelCallback = Callable[[], bool]


def _natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.stem.lower())
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    key.append(path.suffix.lower())
    return key


def _build_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _embedded_image_src(image_path: Path) -> str:
    return _build_data_url(image_path)


def _normalize_second_language(lang2: str | None) -> str | None:
    if not lang2:
        return None
    value = lang2.strip()
    if not value or value == NO_SECOND_LANGUAGE:
        return None
    return value


def _build_prompt_with_languages(primary_language: str, second_language: str | None) -> str:
    lang2 = _normalize_second_language(second_language)
    lang2_line = (
        f'- Fill "turkish_translation" with translation in {lang2}.'
        if lang2
        else '- Set "turkish_translation" to an empty string.'
    )
    language_instruction = (
        "\n\nAdditional language mapping instruction (keep JSON schema and rules exactly as-is):\n"
        f'- Fill "english_translation" with translation in {primary_language}.\n'
        f"{lang2_line}\n"
        '- Do not rename any JSON keys.'
    )
    return PROMPT + language_instruction


def _collect_images(input_dir: Path) -> list[Path]:
    images = sorted(
        [
            p
            for p in input_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ],
        key=_natural_key,
    )
    return images


def _translate_one(
    client: OpenAI,
    image_path: Path,
    model: str,
    prompt_text: str,
    max_output_tokens: int,
    request_timeout: float,
) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = dict(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {"type": "input_image", "image_url": _build_data_url(image_path), "detail": "high"},
                ],
            }
        ],
        max_output_tokens=max_output_tokens,
        timeout=request_timeout,
    )
    if model == "gpt-5-mini":
        request_kwargs["reasoning"] = {"effort": "minimal"}
    elif model.startswith("gpt-5"):
        request_kwargs["reasoning"] = {"effort": "none"}

    response = client.responses.create(**request_kwargs)
    raw_text = response.output_text or ""
    if not raw_text.strip():
        raise RuntimeError(
            f"Model empty output. status={getattr(response, 'status', None)} "
            f"incomplete_details={getattr(response, 'incomplete_details', None)}"
        )
    return _extract_json(raw_text)


def _render_combined_html(
    output_path: Path,
    model: str,
    primary_language: str,
    second_language: str | None,
    items: list[dict[str, Any]],
    total_input_pages: int | None = None,
    cancelled: bool = False,
) -> None:
    lang2 = _normalize_second_language(second_language)
    label1 = html.escape(primary_language)
    label2 = html.escape(lang2) if lang2 else None

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Chapter Translation</title>")
    parts.append("  <style>")
    parts.append("    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; max-width: 1100px; margin: 28px auto; padding: 0 16px; color: #111827; background: #f8fafc; }")
    parts.append("    h1, h2, h3 { margin: 0 0 10px; }")
    parts.append("    .meta { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; margin-bottom: 14px; }")
    parts.append("    .page { background: #fff; border: 1px solid #dbe3ef; border-radius: 12px; padding: 16px; margin-bottom: 20px; }")
    parts.append("    .page-grid { display: flex; gap: 16px; align-items: flex-start; }")
    parts.append(f"    .page-left {{ width: {FIXED_IMAGE_WIDTH_PX}px; flex: 0 0 {FIXED_IMAGE_WIDTH_PX}px; }}")
    parts.append("    .page-right { flex: 1; min-width: 0; }")
    parts.append(
        f"    .page-image {{ width: {FIXED_IMAGE_WIDTH_PX}px; height: {FIXED_IMAGE_HEIGHT_PX}px; "
        "object-fit: contain; border-radius: 10px; border: 1px solid #e5e7eb; margin: 8px auto 14px; display: block; }}"
    )
    parts.append("    @media (max-width: 1100px) { .page-grid { flex-direction: column; } .page-left { width: 100%; flex: 0 0 auto; } }")
    parts.append("    .summary { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; margin-bottom: 12px; }")
    parts.append("    .panel { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px; margin-bottom: 10px; }")
    parts.append("    .label { font-weight: 700; margin-top: 6px; }")
    parts.append("    .text { margin-top: 4px; white-space: normal; }")
    parts.append("    .note { margin-top: 8px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 6px; padding: 8px; color: #9a3412; }")
    parts.append("    .error { margin-top: 8px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 8px; color: #991b1b; }")
    parts.append("    code { background: #f3f4f6; border-radius: 4px; padding: 1px 4px; }")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>Chapter Translation</h1>")
    parts.append('  <div class="meta">')
    parts.append(f"    <div><strong>Model:</strong> <code>{html.escape(model)}</code></div>")
    parts.append(f"    <div><strong>Primary translation language:</strong> <code>{label1}</code></div>")
    parts.append(
        f"    <div><strong>Secondary translation language:</strong> <code>{label2 if label2 else NO_SECOND_LANGUAGE}</code></div>"
    )
    parts.append(f"    <div><strong>Generated at:</strong> <code>{html.escape(dt.datetime.now().isoformat(timespec='seconds'))}</code></div>")
    processed_pages = len(items)
    source_total = total_input_pages if total_input_pages is not None else processed_pages
    parts.append(f"    <div><strong>Processed pages:</strong> {processed_pages}</div>")
    parts.append(f"    <div><strong>Total input pages:</strong> {source_total}</div>")
    if cancelled:
        parts.append("    <div><strong>Status:</strong> <code>Cancelled by user (partial output)</code></div>")
    parts.append("  </div>")

    for idx, item in enumerate(items, start=1):
        image_path = item["image_path"]
        image_src = _embedded_image_src(image_path)
        parts.append('  <section class="page">')
        parts.append(f"    <h2>Page {idx} - {html.escape(image_path.name)}</h2>")
        parts.append('    <div class="page-grid">')
        parts.append('      <div class="page-left">')
        parts.append(f'        <img class="page-image" src="{html.escape(image_src)}" alt="{html.escape(image_path.name)}">')
        parts.append("      </div>")
        parts.append('      <div class="page-right">')

        if "error" in item:
            parts.append(f'        <div class="error"><strong>Translation failed:</strong> {html.escape(item["error"])}</div>')
            parts.append("      </div>")
            parts.append("    </div>")
            parts.append("  </section>")
            continue

        data = item["data"]
        summary = html.escape(str(data.get("page_summary", ""))).replace("\n", "<br>")
        parts.append(f'        <div class="summary"><strong>Page summary (EN):</strong><br>{summary}</div>')

        for panel in _sorted_panels(data):
            number = html.escape(str(panel.get("panel_number", "?")))
            location = html.escape(str(panel.get("panel_location", "")))
            jp = html.escape(str(panel.get("japanese_text", ""))).replace("\n", "<br>")
            text1 = html.escape(str(panel.get("english_translation", ""))).replace("\n", "<br>")
            text2 = html.escape(str(panel.get("turkish_translation", ""))).replace("\n", "<br>")
            note = str(panel.get("uncertainty_note", "")).strip()

            parts.append('        <div class="panel">')
            parts.append(f"          <h3>Panel {number} - {location}</h3>")
            parts.append('          <div class="label">JP</div>')
            parts.append(f'          <div class="text">{jp}</div>')
            parts.append(f'          <div class="label">{label1}</div>')
            parts.append(f'          <div class="text">{text1}</div>')
            if label2:
                parts.append(f'          <div class="label">{label2}</div>')
                parts.append(f'          <div class="text">{text2}</div>')
            if note:
                parts.append(f'          <div class="note"><strong>Note:</strong> {html.escape(note)}</div>')
            parts.append("        </div>")

        parts.append("      </div>")
        parts.append("    </div>")
        parts.append("  </section>")

    parts.append("</body>")
    parts.append("</html>")
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _wrap_pdf_lines(text: str, max_width: float, font_name: str, font_size: float) -> list[str]:
    from reportlab.pdfbase import pdfmetrics

    clean = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for raw_line in clean.split("\n"):
        line = raw_line.strip()
        if not line:
            out.append("")
            continue
        words = line.split()
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if pdfmetrics.stringWidth(trial, font_name, font_size) <= max_width:
                cur = trial
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


def _render_combined_pdf(
    output_path: Path,
    model: str,
    primary_language: str,
    second_language: str | None,
    items: list[dict[str, Any]],
    total_input_pages: int | None = None,
    cancelled: bool = False,
) -> None:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    lang2 = _normalize_second_language(second_language)
    label1 = primary_language
    label2 = lang2

    c = canvas.Canvas(str(output_path), pagesize=landscape(A4))
    page_w, page_h = landscape(A4)
    margin = 26
    left_w = 300
    gap = 16
    right_x = margin + left_w + gap
    right_w = page_w - margin - right_x
    top_y = page_h - margin
    body_bottom = margin + 8

    def _new_page_header(title: str, subtitle: str | None = None) -> float:
        c.setFont("Helvetica-Bold", 15)
        c.drawString(margin, top_y, title)
        y = top_y - 20
        if subtitle:
            c.setFont("Helvetica", 10)
            c.drawString(margin, y, subtitle)
            y -= 14
        return y

    if not items:
        y = _new_page_header("Chapter Translation", f"Model: {model}")
        c.setFont("Helvetica", 11)
        c.drawString(margin, y - 8, "No pages were processed.")
        c.save()
        return

    processed_pages = len(items)
    source_total = total_input_pages if total_input_pages is not None else processed_pages

    for idx, item in enumerate(items, start=1):
        subtitle = (
            f"Model: {model} | Primary: {label1} | Secondary: {label2 if label2 else NO_SECOND_LANGUAGE} | "
            f"Processed: {processed_pages}/{source_total}"
        )
        if cancelled:
            subtitle += " | Status: Cancelled by user (partial output)"
        y = _new_page_header(f"Page {idx} - {item['image_path'].name}", subtitle)

        image_top = y - 2
        image_bottom = body_bottom
        image_h = max(20, image_top - image_bottom)
        c.setStrokeColorRGB(0.86, 0.89, 0.94)
        c.rect(margin, image_bottom, left_w, image_h, stroke=1, fill=0)

        try:
            reader = ImageReader(str(item["image_path"]))
            iw, ih = reader.getSize()
            scale = min(left_w / iw, image_h / ih)
            draw_w = iw * scale
            draw_h = ih * scale
            dx = margin + (left_w - draw_w) / 2
            dy = image_bottom + (image_h - draw_h) / 2
            c.drawImage(reader, dx, dy, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        except Exception:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(margin + 10, image_top - 14, "Image preview unavailable in PDF renderer.")

        text_y = y - 4
        c.setFont("Helvetica", 9)

        def _draw_block(title_text: str, body_text: str, y_pos: float, bold: bool = True) -> tuple[float, bool]:
            if y_pos < body_bottom + 24:
                return y_pos, False
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
            c.drawString(right_x, y_pos, title_text)
            y_pos -= 12
            c.setFont("Helvetica", 9)
            for line in _wrap_pdf_lines(body_text, right_w, "Helvetica", 9):
                if y_pos < body_bottom + 12:
                    return y_pos, False
                c.drawString(right_x, y_pos, line)
                y_pos -= 11
            return y_pos - 4, True

        if "error" in item:
            text_y, _ = _draw_block("Translation failed:", str(item["error"]), text_y)
            c.showPage()
            continue

        data = item["data"]
        text_y, ok = _draw_block("Page summary (EN):", str(data.get("page_summary", "")), text_y)
        if not ok:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(right_x, body_bottom + 4, "...truncated")
            c.showPage()
            continue

        truncated = False
        for panel in _sorted_panels(data):
            heading = f"Panel {panel.get('panel_number', '?')} - {panel.get('panel_location', '')}"
            text_y, ok = _draw_block(heading, "", text_y)
            if not ok:
                truncated = True
                break
            text_y, ok = _draw_block("JP:", str(panel.get("japanese_text", "")), text_y, bold=False)
            if not ok:
                truncated = True
                break
            text_y, ok = _draw_block(f"{label1}:", str(panel.get("english_translation", "")), text_y, bold=False)
            if not ok:
                truncated = True
                break
            if label2:
                text_y, ok = _draw_block(f"{label2}:", str(panel.get("turkish_translation", "")), text_y, bold=False)
                if not ok:
                    truncated = True
                    break
            note = str(panel.get("uncertainty_note", "")).strip()
            if note:
                text_y, ok = _draw_block("Note:", note, text_y, bold=False)
                if not ok:
                    truncated = True
                    break

        if truncated:
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(right_x, body_bottom + 4, "...truncated")

        c.showPage()

    c.save()


def translate_chapter_to_single_html(
    input_dir: Path,
    output_path: Path,
    model: str,
    api_key: str,
    primary_language: str,
    second_language: str | None,
    max_output_tokens: int = 5000,
    request_timeout: float = 180.0,
    progress_callback: ProgressCallback | None = None,
    cancel_requested: CancelCallback | None = None,
    output_format: str = "auto",
) -> tuple[Path, int, int, bool, int]:
    if model not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model: {model}")
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")
    if not primary_language:
        raise ValueError("Primary language is required.")

    images = _collect_images(input_dir)
    if not images:
        raise RuntimeError(f"No image files found in {input_dir}")

    total = len(images)
    if progress_callback:
        progress_callback("total", 0, total, "Pages detected", True)

    prompt_text = _build_prompt_with_languages(primary_language, second_language)
    client = OpenAI(api_key=api_key)
    results: list[dict[str, Any]] = []
    cancelled = False

    for idx, image_path in enumerate(images, start=1):
        if cancel_requested and cancel_requested():
            cancelled = True
            break
        if progress_callback:
            progress_callback("page_start", idx, total, image_path.name, True)
        try:
            data = _translate_one(
                client=client,
                image_path=image_path,
                model=model,
                prompt_text=prompt_text,
                max_output_tokens=max_output_tokens,
                request_timeout=request_timeout,
            )
            results.append({"image_path": image_path, "data": data})
            if progress_callback:
                progress_callback("page_done", idx, total, image_path.name, True)
        except (RateLimitError, APIConnectionError, BadRequestError, RuntimeError, ValueError) as exc:
            msg = str(exc)
            results.append({"image_path": image_path, "error": msg})
            if progress_callback:
                progress_callback("page_done", idx, total, f"{image_path.name}: {msg}", False)

    fmt = output_format.lower().strip()
    if fmt == "auto":
        fmt = "pdf" if output_path.suffix.lower() == ".pdf" else "html"
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {fmt}")

    if fmt == "html":
        _render_combined_html(
            output_path=output_path,
            model=model,
            primary_language=primary_language,
            second_language=second_language,
            items=results,
            total_input_pages=total,
            cancelled=cancelled,
        )
    else:
        _render_combined_pdf(
            output_path=output_path,
            model=model,
            primary_language=primary_language,
            second_language=second_language,
            items=results,
            total_input_pages=total,
            cancelled=cancelled,
        )
    failures = sum(1 for item in results if "error" in item)
    if progress_callback:
        if cancelled:
            progress_callback("cancelled", len(results), total, str(output_path), True)
        else:
            progress_callback("finished", total, total, str(output_path), failures == 0)
    return output_path, total, failures, cancelled, len(results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate all manga pages in a folder and save as one combined HTML."
    )
    parser.add_argument("--input-dir", required=True, type=Path, help="Folder containing page images.")
    parser.add_argument("--output", type=Path, help="Combined HTML output path.")
    parser.add_argument("--model", default="gpt-4.1", choices=SUPPORTED_MODELS, help="OpenAI model name.")
    parser.add_argument("--api-key", default=None, help="Optional API key. Defaults to OPENAI_API_KEY.")
    parser.add_argument("--lang1", default="English", choices=SUPPORTED_LANGUAGES, help="Primary translation language.")
    parser.add_argument(
        "--lang2",
        default="Turkish",
        choices=[NO_SECOND_LANGUAGE] + SUPPORTED_LANGUAGES,
        help="Secondary translation language (or (None)).",
    )
    parser.add_argument("--max-output-tokens", type=int, default=5000, help="Max output tokens per page.")
    parser.add_argument("--request-timeout", type=float, default=180.0, help="Timeout seconds per page request.")
    parser.add_argument(
        "--output-format",
        default="auto",
        choices=["auto"] + SUPPORTED_OUTPUT_FORMATS,
        help="Output format: auto/html/pdf. Auto infers from --output extension.",
    )
    args = parser.parse_args()

    key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set. Use env var or --api-key.")

    output_path = args.output or args.input_dir / "chapter_translation.html"

    def _cli_progress(stage: str, index: int, total: int, message: str, success: bool) -> None:
        if stage == "page_start":
            print(f"[{index}/{total}] Translating {message} ...", flush=True)
        elif stage == "page_done":
            status = "OK" if success else "FAIL"
            print(f"[{index}/{total}] {status}: {message}", flush=True)

    saved_path, total_pages, failures, cancelled, processed_pages = translate_chapter_to_single_html(
        input_dir=args.input_dir,
        output_path=output_path,
        model=args.model,
        api_key=key,
        primary_language=args.lang1,
        second_language=args.lang2,
        max_output_tokens=args.max_output_tokens,
        request_timeout=args.request_timeout,
        progress_callback=_cli_progress,
        output_format=args.output_format,
    )

    print(f"Combined HTML saved: {saved_path}", flush=True)
    print(
        f"Pages processed: {processed_pages}/{total_pages}, failures: {failures}, cancelled: {cancelled}",
        flush=True,
    )


if __name__ == "__main__":
    main()
