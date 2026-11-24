# 🌐 Otel DM Demo — Erişim Linkleri ve Canlıya Taşıma Rehberi

Bu rehber, demoyu hem kendi bilgisayarınızda hem de **müşterilerin/otel sahiplerinin cep telefonlarında** canlı olarak test edebilmeniz için gereken tüm yolları içerir.

---

## 1. Lokal Çalışma (Kendi Bilgisayarınızda)

- 👉 **Web Demo Adresi:** [http://localhost:8000](http://localhost:8000)
- 👉 **Sağlık Kontrolü (API):** [http://localhost:8000/health](http://localhost:8000/health)

Tek tıkla başlatmak için:
- 🚀 **`web_demo_baslat.bat`** dosyasına çift tıklayın.

---

## 2. Anında Canlı Mobil Link (Hemen Şimdi Telefonda Test Etmek İçin)

Otel sahibine toplantıda veya telefondayken anında bir canlı link vermek isterseniz:

1. Sunucu açıkken klasördeki **`canli_mobil_link.bat`** dosyasına çift tıklayın.
2. Açılan siyah pencerede `https://xxxx.lhr.life` şeklinde yeşil renkli bir HTTPS linki görünecektir.
3. Bu linki **kendi telefonunuza veya müşteriye WhatsApp'tan atın**. Tarayıcıda doğrudan mobil Instagram DM ekranı gibi açılır ve test edilebilir.

---

## 3. Kalıcı 7/24 Bulut Dağıtımı (Railway veya Render)

Bilgisayarınız kapalı olsa dahi demoun 7/24 internette canlı kalması için en ideal iki platform:

### Seçenek A: Railway.app (En Kolayı — Proje Dosyaları Zaten Hazır)

1. [Railway.app](https://railway.app) adresine gidin ve GitHub hesabınızla giriş yapın.
2. **"New Project" -> "Deploy from GitHub repo"** seçin ve bu depoyu seçin (veya Root Directory olarak `Projeler/Otel_DM_Demo` belirtin).
3. Klasördeki [railway.json](file:///c:/Users/geasy/OneDrive/Masaüstü/Antigravity_Starter_Kit/Antigravity2/Projeler/Otel_DM_Demo/railway.json) ve [Procfile](file:///c:/Users/geasy/OneDrive/Masaüstü/Antigravity_Starter_Kit/Antigravity2/Projeler/Otel_DM_Demo/Procfile) sayesinde Railway sistemi otomatik algılar.
4. **Variables (Ortam Değişkenleri)** sekmesine şu anahtarları ekleyin:
   - `OPENAI_API_KEY`: OpenAI API anahtarınız
   - `HOTEL_AGENT_MODEL`: `gpt-4o-mini`
   - `TELEGRAM_BOT_TOKEN`: Telegram bot tokenınız
   - `ADMIN_CHAT_ID`: Telegram bildirim chat ID'niz
5. **Settings -> Networking -> Generate Domain** butonuna tıklayın. Size özel `https://otel-demo-production.up.railway.app` gibi kalıcı bir domain üretilir.

---

### Seçenek B: Render.com (Ücretsiz Başlangıç)

1. [Render.com](https://render.com) adresine gidin.
2. **New + -> Web Service** seçeneğine tıklayın.
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. **Environment Variables** bölümüne yukarıdaki 4 değişkeni (`OPENAI_API_KEY` vb.) girin ve **Create Web Service** butonuna basın.
