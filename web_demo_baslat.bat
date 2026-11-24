@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo Korykos Boutique Hotel ^& Beach — Web Demo Baslatiliyor...
echo Tarayicida http://localhost:8000 acilacak.
echo (Sunucuyu kapatmak icin bu pencereyi kapatabilirsiniz.)
echo ========================================================
start "" "http://localhost:8000"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" main.py
pause

