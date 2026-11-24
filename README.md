# Otel DM Demo Botu — Korykos Boutique Hotel & Beach (Mersin Kızkalesi)

Çukurova bölgesindeki butik ve büyümek isteyen otellere **AI destekli Instagram & WhatsApp DM Otomasyonu** satışı yapmak için hazırlanmış, uçtan uca çalışan demo projesidir.

> **Önemli:** Bu proje `Projeler/Otel_Danisma_Asistani` projesinin mimarisini temel alır ancak orijinal projeye **hiç dokunmadan** tamamen bağımsız bir klasörde (`Projeler/Otel_DM_Demo`) çalışır.

## Neler Yapar?

1. **7/24 Çok Dilli Misafir İletişimi:** Türkçe, İngilizce, Rusça ve Almanca dillerinde misafirin yazdığı dili algılayıp o dilde yanıt verir.
2. **Gerçekçi Fiyat & Müsaitlik Hesaplama (`hotelrunner.py`):**
   - Standart Bahçe Odası, Deluxe Deniz Manzaralı Oda, Aile Odası ve Jakuzili Teras Suit için hem **Oda + Kahvaltı** hem **Yarım Pansiyon** fiyatlarını sezon ve kişi sayısına göre hesaplar.
   - 12 yaş ve üzeri çocukları otomatik yetişkin sayar ve şeffafça açıklar.
   - İstenen tarih doluysa (ör. 15 Ağustos veya 18 Temmuz) yakın tarihleri otomatik tarayıp müsait alternatif önerir.
   - Fiyat uydurmayı engelleyen deterministik güvenlik kapısı (`decisions.py`) içerir.
3. **Oda ve Tesis Fotoğrafı Gönderme (`images.py`):** Misafir fotoğraf istediğinde veya belirli bir odayı sorduğunda ilgili odanın/plajın görsellerini otomatik paylaşır.
4. **Sesli Mesaj ve Görsel Anlama (`llm.py`, `vision.py`):** OpenAI `gpt-4o-mini-transcribe` ile sesli mesajları metne çevirir, `gpt-4o-mini` ile misafirin attığı görselleri inceler.
5. **Canlı Personele Devir / Escalation (`escalation.py`):** Şikâyet, oda arızası, özel indirim pazarlığı veya "beni arayın" taleplerinde otel yetkilisine **Telegram** üzerinden anında bildirim gönderir.

## 🌐 Canlı Web Demo Linki

- **Tarayıcı Demo Ekranı:** [http://localhost:8000](http://localhost:8000)
- **Tek Tıkla Başlatıcı:** Klasördeki `web_demo_baslat.bat` dosyasına çift tıkladığınızda sunucu çalışır ve tarayıcıda demo ekranı otomatik açılır. (Detaylar: `DEMO_LINKI.md`)

## Hızlı Başlangıç (Lokal)

Anahtarlar kök dizindeki `_knowledge/credentials/master.env` dosyasından otomatik okunur (`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`).

### 1. Terminalden Canlı Sohbet
```bash
python main.py --cli
```

### 2. 20 Senaryoluk Otomatik Demo Sınavı (4 Dil)
```bash
python demo_sinav.py
```

### 3. Web Servisi Olarak Çalıştırma
```bash
uvicorn main:app --reload --port 8000
```

