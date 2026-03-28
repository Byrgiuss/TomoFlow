#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from openai import APIConnectionError, OpenAI, RateLimitError


PROMPT = """You are a professional manga translator and layout reader.

Analyze the provided Japanese manga page and extract dialogue/narration text panel by panel.

Rules:
1) Assume Japanese manga reading order: panels are read right-to-left within each row, and rows top-to-bottom.
2) For each panel, provide a short location label such as "right top panel", "left top panel", "center panel", "right bottom panel".
3) Keep the original Japanese text exactly as visible (best effort OCR).
4) Translate each extracted text into English and Turkish.
5) If text is unclear, include your best guess and add an uncertainty note.
6) Return ONLY valid JSON (no markdown fences, no extra commentary).

Return this JSON schema:
{
  "page_summary": "short one-line summary of page content in English",
  "panels": [
    {
      "panel_number": 1,
      "panel_location": "right top panel",
      "japanese_text": "....",
      "english_translation": "....",
      "turkish_translation": "....",
      "uncertainty_note": ""
    }
  ]
}
"""


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


def _extract_json(raw_text: str) -> dict[str, Any]:
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    if "```" in raw_text:
        pieces = raw_text.split("```")
        for piece in pieces:
            candidate = piece.replace("json", "", 1).strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw_text[start : end + 1]
        return json.loads(candidate)

    raise ValueError("API cevabi parse edilemedi: gecerli JSON bulunamadi.")


def _sorted_panels(data: dict[str, Any]) -> list[dict[str, Any]]:
    panels = data.get("panels", [])
    if not isinstance(panels, list):
        return []
    return sorted(
        (p for p in panels if isinstance(p, dict)),
        key=lambda p: (p.get("panel_number") if isinstance(p.get("panel_number"), int) else 10**9),
    )


def _write_output_txt(
    output_path: Path,
    image_path: Path,
    model: str,
    reasoning_effort: str,
    data: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append(f"Source image: {image_path}")
    lines.append(f"Model: {model}")
    lines.append(f"Reasoning effort: {reasoning_effort}")
    lines.append(f"Generated at: {dt.datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Page summary (EN): {data.get('page_summary', '')}")
    lines.append("")
    lines.append("Panels:")

    for panel in _sorted_panels(data):
        lines.append("")
        lines.append(f"Panel {panel.get('panel_number', '?')} - {panel.get('panel_location', '')}")
        lines.append(f"JP: {panel.get('japanese_text', '')}")
        lines.append(f"EN: {panel.get('english_translation', '')}")
        lines.append(f"TR: {panel.get('turkish_translation', '')}")
        note = panel.get("uncertainty_note", "")
        if note:
            lines.append(f"Note: {note}")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_output_md(
    output_path: Path,
    image_path: Path,
    model: str,
    reasoning_effort: str,
    data: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Manga Translation")
    lines.append("")
    lines.append(f"- Source image: `{image_path}`")
    lines.append(f"- Model: `{model}`")
    lines.append(f"- Reasoning effort: `{reasoning_effort}`")
    lines.append(f"- Generated at: `{dt.datetime.now().isoformat(timespec='seconds')}`")
    lines.append("")
    lines.append("## Page Summary (EN)")
    lines.append("")
    lines.append(str(data.get("page_summary", "")))
    lines.append("")
    lines.append("## Panels")

    for panel in _sorted_panels(data):
        lines.append("")
        lines.append(f"### Panel {panel.get('panel_number', '?')} - {panel.get('panel_location', '')}")
        lines.append("")
        lines.append("**JP**")
        lines.append("")
        lines.append(str(panel.get("japanese_text", "")))
        lines.append("")
        lines.append("**EN**")
        lines.append("")
        lines.append(str(panel.get("english_translation", "")))
        lines.append("")
        lines.append("**TR**")
        lines.append("")
        lines.append(str(panel.get("turkish_translation", "")))
        note = str(panel.get("uncertainty_note", "")).strip()
        if note:
            lines.append("")
            lines.append(f"> Note: {note}")

    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _nl2br(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def _image_src_for_html(image_path: Path, output_path: Path) -> str | None:
    try:
        resolved_image = image_path.resolve()
        resolved_output_dir = output_path.parent.resolve()
        rel_path = os.path.relpath(resolved_image, resolved_output_dir)
        rel_posix = Path(rel_path).as_posix()
        return quote(rel_posix, safe="/._-~")
    except Exception:
        raw = str(image_path).strip()
        if not raw:
            return None
        return quote(Path(raw).as_posix(), safe="/._-~")


def _write_output_html(
    output_path: Path,
    image_path: Path,
    model: str,
    reasoning_effort: str,
    data: dict[str, Any],
) -> None:
    generated_at = dt.datetime.now().isoformat(timespec="seconds")
    page_summary = _nl2br(str(data.get("page_summary", "")))
    image_src = _image_src_for_html(image_path, output_path)

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Manga Translation</title>")
    parts.append("  <style>")
    parts.append("    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; max-width: 980px; margin: 32px auto; padding: 0 16px; color: #1f2937; background: #f8fafc; }")
    parts.append("    h1, h2, h3 { margin: 0 0 12px; }")
    parts.append("    .meta { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin-bottom: 18px; }")
    parts.append("    .summary { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin-bottom: 18px; }")
    parts.append("    .page-image-wrap { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin-bottom: 18px; }")
    parts.append("    .page-image { width: 100%; height: auto; border-radius: 8px; display: block; }")
    parts.append("    .page-image-caption { font-size: 13px; color: #4b5563; margin-top: 8px; word-break: break-all; }")
    parts.append("    .panel { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; margin-bottom: 12px; }")
    parts.append("    .label { font-weight: 700; color: #111827; margin-top: 8px; }")
    parts.append("    .text { white-space: normal; margin-top: 4px; color: #111827; }")
    parts.append("    .note { margin-top: 10px; padding: 8px 10px; border-radius: 8px; background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; }")
    parts.append("    code { background: #f3f4f6; border-radius: 5px; padding: 1px 4px; }")
    parts.append("  </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("  <h1>Manga Translation</h1>")
    parts.append('  <div class="meta">')
    parts.append(f"    <div><strong>Source image:</strong> <code>{html.escape(str(image_path))}</code></div>")
    parts.append(f"    <div><strong>Model:</strong> <code>{html.escape(model)}</code></div>")
    parts.append(f"    <div><strong>Reasoning effort:</strong> <code>{html.escape(reasoning_effort)}</code></div>")
    parts.append(f"    <div><strong>Generated at:</strong> <code>{html.escape(generated_at)}</code></div>")
    parts.append("  </div>")
    parts.append("  <h2>Page Image</h2>")
    parts.append('  <div class="page-image-wrap">')
    if image_src:
        parts.append(
            f'    <img class="page-image" src="{html.escape(image_src)}" alt="Manga page image">'
        )
    else:
        parts.append("    <div>Image path unavailable.</div>")
    parts.append(f'    <div class="page-image-caption">{html.escape(str(image_path))}</div>')
    parts.append("  </div>")
    parts.append("  <h2>Page Summary (EN)</h2>")
    parts.append(f'  <div class="summary">{page_summary}</div>')
    parts.append("  <h2>Panels</h2>")

    for panel in _sorted_panels(data):
        num = html.escape(str(panel.get("panel_number", "?")))
        loc = html.escape(str(panel.get("panel_location", "")))
        jp = _nl2br(str(panel.get("japanese_text", "")))
        en = _nl2br(str(panel.get("english_translation", "")))
        tr = _nl2br(str(panel.get("turkish_translation", "")))
        note = str(panel.get("uncertainty_note", "")).strip()

        parts.append('  <section class="panel">')
        parts.append(f"    <h3>Panel {num} - {loc}</h3>")
        parts.append('    <div class="label">JP</div>')
        parts.append(f'    <div class="text">{jp}</div>')
        parts.append('    <div class="label">EN</div>')
        parts.append(f'    <div class="text">{en}</div>')
        parts.append('    <div class="label">TR</div>')
        parts.append(f'    <div class="text">{tr}</div>')
        if note:
            parts.append(f'    <div class="note"><strong>Note:</strong> {_nl2br(note)}</div>')
        parts.append("  </section>")

    parts.append("</body>")
    parts.append("</html>")
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _write_output(
    output_path: Path,
    output_format: str,
    image_path: Path,
    model: str,
    reasoning_effort: str,
    data: dict[str, Any],
) -> None:
    if output_format == "txt":
        _write_output_txt(output_path, image_path, model, reasoning_effort, data)
        return
    if output_format == "md":
        _write_output_md(output_path, image_path, model, reasoning_effort, data)
        return
    if output_format == "html":
        _write_output_html(output_path, image_path, model, reasoning_effort, data)
        return
    raise ValueError(f"Desteklenmeyen output format: {output_format}")


def _resolve_output_format(requested_format: str, output_path: Path | None) -> str:
    if requested_format != "auto":
        return requested_format
    if output_path:
        suffix = output_path.suffix.lower()
        if suffix == ".txt":
            return "txt"
        if suffix in {".md", ".markdown"}:
            return "md"
        if suffix in {".html", ".htm"}:
            return "html"
    return "html"


def _default_output_path(image_path: Path, output_format: str) -> Path:
    ext = {"txt": "txt", "md": "md", "html": "html"}[output_format]
    return image_path.with_name(f"{image_path.stem}_translation.{ext}")


def _parse_translation_txt(input_txt: Path) -> tuple[Path, str, str, dict[str, Any]]:
    source_image = Path("")
    model = "unknown"
    reasoning_effort = "unknown"
    page_summary = ""
    panels: list[dict[str, Any]] = []
    current_panel: dict[str, Any] | None = None
    current_field: str | None = None
    in_panels = False

    def finalize_panel() -> None:
        nonlocal current_panel
        if current_panel is not None:
            panels.append(current_panel)
            current_panel = None

    for raw_line in input_txt.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("Source image: "):
            source_image = Path(line[len("Source image: ") :].strip())
            continue
        if line.startswith("Model: "):
            model = line[len("Model: ") :].strip()
            continue
        if line.startswith("Reasoning effort: "):
            reasoning_effort = line[len("Reasoning effort: ") :].strip()
            continue
        if line.startswith("Page summary (EN): "):
            page_summary = line[len("Page summary (EN): ") :].strip()
            continue
        if line.strip() == "Panels:":
            in_panels = True
            continue

        if not in_panels:
            continue

        if line.startswith("Panel "):
            finalize_panel()
            panel_no = None
            panel_loc = ""
            header = line[len("Panel ") :]
            if " - " in header:
                left, right = header.split(" - ", 1)
                panel_loc = right.strip()
            else:
                left = header
            try:
                panel_no = int(left.strip())
            except ValueError:
                panel_no = None
            current_panel = {
                "panel_number": panel_no,
                "panel_location": panel_loc,
                "japanese_text": "",
                "english_translation": "",
                "turkish_translation": "",
                "uncertainty_note": "",
            }
            current_field = None
            continue

        if current_panel is None:
            continue

        if line.startswith("JP: "):
            current_field = "japanese_text"
            current_panel[current_field] = line[len("JP: ") :]
            continue
        if line.startswith("EN: "):
            current_field = "english_translation"
            current_panel[current_field] = line[len("EN: ") :]
            continue
        if line.startswith("TR: "):
            current_field = "turkish_translation"
            current_panel[current_field] = line[len("TR: ") :]
            continue
        if line.startswith("Note: "):
            current_field = "uncertainty_note"
            current_panel[current_field] = line[len("Note: ") :]
            continue

        if current_field is not None:
            current_panel[current_field] = f"{current_panel.get(current_field, '')}\n{line}".strip("\n")

    finalize_panel()
    if not str(source_image):
        source_image = input_txt
    data = {"page_summary": page_summary, "panels": panels}
    return source_image, model, reasoning_effort, data


def translate_one_page(
    image_path: Path,
    output_path: Path,
    output_format: str,
    model: str,
    reasoning_effort: str,
    api_key: str | None,
    max_output_tokens: int,
    request_timeout: float,
) -> None:
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY tanimli degil. Ortam degiskeni veya --api-key verin.")

    client = OpenAI(api_key=key)
    data_url = _build_data_url(image_path)

    if model.startswith("gpt-5.4-pro") and reasoning_effort in {"none", "minimal", "low"}:
        raise ValueError("gpt-5.4-pro icin reasoning-effort 'medium', 'high' veya 'xhigh' olmali.")

    request_kwargs: dict[str, Any] = dict(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            }
        ],
        max_output_tokens=max_output_tokens,
        timeout=request_timeout,
    )
    if model.startswith("gpt-5"):
        request_kwargs["reasoning"] = {"effort": reasoning_effort}

    try:
        response = client.responses.create(**request_kwargs)
    except RateLimitError as exc:
        raise RuntimeError(
            "OpenAI API 429 (insufficient_quota). Lutfen billing/kota durumunu kontrol edin."
        ) from exc
    except APIConnectionError as exc:
        raise RuntimeError(
            "OpenAI API baglanti hatasi. Ag erisimi veya DNS sorununu kontrol edin."
        ) from exc

    raw_text = response.output_text or ""
    if not raw_text.strip():
        raise RuntimeError(
            f"Model bos metin dondu. status={getattr(response, 'status', None)}, "
            f"incomplete_details={getattr(response, 'incomplete_details', None)}. "
            "GPT-5 icin reasoning-effort'u dusurun veya max-output-tokens'i artirin."
        )
    parsed = _extract_json(raw_text)
    _write_output(output_path, output_format, image_path, model, reasoning_effort, parsed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate one Japanese manga page image into English and Turkish, panel by panel."
    )
    parser.add_argument("--image", type=Path, help="Input image path (PNG/JPG/WebP).")
    parser.add_argument(
        "--from-txt",
        type=Path,
        help="Reformat an existing translation .txt file without calling API.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path. If omitted, created as <image_stem>_translation.<ext>",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "txt", "md", "html"],
        help="Output format (default: auto -> infer from --output or html).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1",
        help="OpenAI model name (default: gpt-4.1).",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="none",
        choices=["none", "minimal", "low", "medium", "high", "xhigh"],
        help="Reasoning effort for GPT-5 models (default: none).",
    )
    parser.add_argument("--api-key", default=None, help="Optional API key. Defaults to OPENAI_API_KEY env var.")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=5000,
        help="Maximum output tokens for model response.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=180.0,
        help="Per-request timeout in seconds (default: 180).",
    )
    args = parser.parse_args()

    if args.from_txt and args.image:
        parser.error("Ayni anda hem --image hem --from-txt verme. Birini sec.")
    if not args.from_txt and not args.image:
        parser.error("--image gerekli. Alternatif olarak --from-txt kullanabilirsin.")

    output_format = _resolve_output_format(args.format, args.output)
    if args.from_txt:
        output_path = args.output or args.from_txt.with_name(
            f"{args.from_txt.stem}_formatted.{ {'txt':'txt','md':'md','html':'html'}[output_format] }"
        )
        src_image, model, reasoning_effort, data = _parse_translation_txt(args.from_txt)
        _write_output(output_path, output_format, src_image, model, reasoning_effort, data)
        print(f"Formatted output saved to: {output_path}")
        return

    output_path = args.output or _default_output_path(args.image, output_format)
    translate_one_page(
        image_path=args.image,
        output_path=output_path,
        output_format=output_format,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        api_key=args.api_key,
        max_output_tokens=args.max_output_tokens,
        request_timeout=args.request_timeout,
    )
    print(f"Translation saved to: {output_path}")


if __name__ == "__main__":
    main()
