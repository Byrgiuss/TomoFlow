@echo off
setlocal

cd /d %~dp0

if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\activate
pip install -r requirements.txt pyinstaller

if not exist assets\TomoFlowLogo.ico (
  py -3 -c "from PIL import Image; Image.open('assets/TomoFlowLogo.png').save('assets/TomoFlowLogo.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
)

pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --icon assets\TomoFlowLogo.ico ^
  --add-data "assets\TomoFlowLogo.png;." ^
  --name TomoFlow ^
  src\manga_translator_app.py

echo Build complete: dist\TomoFlow\TomoFlow.exe
endlocal
