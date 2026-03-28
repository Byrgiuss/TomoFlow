<div align="center">
  <img src="assets/TomoFlowLogo.png" alt="TomoFlow Logo" width="220" />
  <h1>TomoFlow</h1>
  <p><strong>Panel-aware manga translation workflow powered by OpenAI vision models.</strong></p>
  <p>
    <a href="https://github.com/Byrgiuss/"><img alt="Author" src="https://img.shields.io/badge/Byrgiuss-2026-black"></a>
    <img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  </p>
</div>

## What Is TomoFlow?
TomoFlow translates Japanese manga page images panel-by-panel, preserves manga reading flow (right-to-left, top-to-bottom), and exports a clean, readable output (`HTML` or `PDF`) with:
- page image on the left
- panel text + translations on the right

It is designed for fan-translation workflows where readability and panel context matter.

## Key Features
- Sequential page processing (stable chapter order)
- Panel-level extraction and structured output
- Primary + optional secondary translation language
- Broad model support (`gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `gpt-5-mini`, `gpt-5.4`)
- Standalone output option with embedded page images
- GUI with:
  - model and language selectors
  - progress bar
  - cancel/stop flow with confirmation
  - API key save/clear
  - Help and About dialogs

## Visual Workflow
```mermaid
flowchart LR
  A[Input Folder<br/>PNG/JPG/WEBP pages] --> B[Page-by-page API calls]
  B --> C[Panel detection/order mapping<br/>RTL + top-to-bottom]
  C --> D[Translations in selected language(s)]
  D --> E[Single output file<br/>HTML or PDF]
```

## Repository Structure
```text
TomoFlow_GitHub_Ready/
├── assets/
│   ├── TomoFlowLogo.png
│   └── TomoFlowLogo.ico
├── dist/
│   ├── mac/
│   │   └── TomoFlow.app
│   └── windows/
│       └── BUILD_ON_WINDOWS.md
├── src/
│   ├── manga_translator_app.py
│   ├── translate_chapter_single_html.py
│   └── translate_single_page.py
├── tools/
│   └── html_to_pdf.py
├── .github/workflows/
│   └── build.yml
├── build_mac_app.sh
├── build_windows_exe.bat
├── requirements.txt
└── README.md
```

## Ready Distributions
- macOS ready app: `dist/mac/TomoFlow.app`
- Windows build target: `dist/TomoFlow/TomoFlow.exe` (generate on Windows via `build_windows_exe.bat`)

## Quick Start (Source)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 src/manga_translator_app.py
```

## Build Commands
### macOS
```bash
chmod +x build_mac_app.sh
./build_mac_app.sh
```
Output: `dist/TomoFlow.app`

### Windows
```bat
build_windows_exe.bat
```
Output: `dist\TomoFlow\TomoFlow.exe`

## GUI Fields
- `Input Folder`: chapter image folder
- `Output Path`: target HTML/PDF path
- `Output Format`: HTML or PDF
- `OpenAI API Key`: masked input, locally stored
- `Clear Key`: remove saved key
- `Model`: choose GPT model
- `Language 1`: required
- `Language 2`: optional
- `Start Translation`: start process
- `Cancel Translation`: stop with confirmation, save partial result

## Notes
- Use your own OpenAI API key.
- The app can produce partial output if cancellation happens mid-run.
- For reproducible releases on both OSes, use `.github/workflows/build.yml`.

## Credits
- Created by Byrgiuss (2026)
- Profile: https://github.com/Byrgiuss/
