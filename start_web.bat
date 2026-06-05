@echo off
cd /d "%~dp0"
echo 対旋律作成ツール Webアプリを起動中...
echo ブラウザで http://localhost:5000 を開いてください
start "" "http://localhost:5000"
python app.py
pause
