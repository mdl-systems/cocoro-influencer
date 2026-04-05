@echo off
title [%~nx0] Avatar Hybrid Video Pipeline
echo ===================================================
echo   🎬 商用APIハイブリッド・アバター動画サーバー 🎬
echo ===================================================
echo [info] 仮想環境に移行してFastAPIを起動します...

call "f:\antigravity\venv\Scripts\activate.bat"

echo.
echo [info] Webサーバー（API）起動中...
echo.
echo 🌐 起動完了後、以下のURLをブラウザで開いてください：
echo 👉 http://localhost:8082
echo.

python api/server.py

pause
