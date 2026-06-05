@echo off
cd /d "%~dp0"
:: ウィンドウを非表示でFlaskを起動し、ブラウザを開く
start "" /min cmd /c "python app.py"
timeout /t 3 /nobreak >nul
start "" "http://localhost:5000"
