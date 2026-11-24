@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===================================================================
echo   🌐 Otel DM Demo — Canli Mobil / Internet Linki Olusturuluyor
echo ===================================================================
echo.
echo 1. Arka planda sunucunun acik oldugundan emin olun (web_demo_baslat.bat).
echo 2. Asagidaki baglanti kuruldugunda ekranda cikan "https://...lhr.life" 
echo    linkini telefonunuzdan acabilir veya WhatsApp ile paylasabilirsiniz.
echo.
echo Link olusturuluyor, lutfen bekleyin...
echo (Kapatmak icin bu pencereyi kapatabilirsiniz.)
echo ===================================================================
echo.
ssh -o StrictHostKeyChecking=no -R 80:localhost:8000 nokey@localhost.run
pause

