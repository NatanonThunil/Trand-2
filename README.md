<div align="center">

# 📈 Pro Trading Telegram Bot (Stocks & Crypto)
**Advanced Market Scanner & Technical Analysis Bot**

[![Python Version](https://img.shields.io/badge/Python-3.10+-blue.svg?style=flat&logo=python)](https://www.python.org/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot--API-2CA5E0.svg?style=flat&logo=telegram)](https://core.telegram.org/bots/api)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248.svg?style=flat&logo=mongodb)](https://www.mongodb.com/)
[![Render](https://img.shields.io/badge/Hosted%20On-Render-46E3B7.svg?style=flat&logo=render)](https://render.com/)

🌍 **Choose Language:** [🇬🇧 English](#-english-version) | [🇹🇭 ภาษาไทย](#-เวอร์ชันภาษาไทย-thai-version)

</div>


## 🇬🇧 English Version

An advanced Telegram Bot designed for traders. It automatically scans global markets (US, China, Hong Kong, Thailand, and Crypto) to find the best trading setups using Multi-Dimensional Technical Analysis (EMA, MACD, RSI, Bollinger Bands, ATR, and Volume).

### ✨ Key Features
- **🌍 Global Market Scanner:** Scans 5 major markets (TH, CN, HK, US, CRYPTO) for Top 5 Buy/Sell signals.
- **🧠 Smart Stateful Scanning:** Remembers previous top picks and only scans to replace symbols that lost their momentum, making scans lightning fast.
- **📊 Pro Chart Generation:** Generates high-quality candlestick charts (`mplfinance`) with automatically plotted entry, TP, SL, and technical indicators.
- **🔔 Price Alerts & Daily Notify:** Set custom price alerts and receive a daily global market summary every morning.
- **💾 Persistent Storage:** Integrated with MongoDB Atlas. User data, alerts, and market cache survive server restarts.
- **⚡ High Concurrency:** Built with `asyncio` and `ThreadPoolExecutor` (Fire-and-Forget architecture) to handle multiple users simultaneously without bottlenecking.
- **🛡️ Anti-Sleep System:** Built-in web server and self-ping mechanism to keep the Render free-tier active.

### 🕹️ Commands
| Command | Description |
| :--- | :--- |
| `/start` | Start the bot and get the user guide. |
| `/signal <SYMBOL> <EXCHANGE>` | Analyze a specific asset and generate a Pro Chart (e.g., `/signal BTCUSDT BINANCE`). |
| `/alert <SYMBOL> <EXCHANGE> <above/below> <PRICE>` | Set a custom price alert (e.g., `/alert AAPL NASDAQ above 200`). |
| `/top_all` | Get the Top 3 Buy signals across all global markets. |
| `/top_th`, `/top_us`, `/top_crypto` | Get the Top 5 Buy signals for a specific market. |
| `/top_sell_all` | Get the Top 3 Sell/Downtrend warnings across all markets. |
| `/top_on` / `/top_off` | Turn on/off daily morning market summary notifications. |

### 🚀 Installation & Setup

1. **Clone the repository:**

   git clone [[https://github.com/yourusername/your-repo-name.git](https://github.com/yourusername/your-repo-name.git)](https://github.com/NatanonThunil/Trand-2.git)
   cd your-repo-name


2. **Install requirements:**
```bash
pip install -r requirements.txt

```


3. **Environment Variables (`.env`):**
Create a `.env` file in the root directory and add the following:
```env
BOT_TOKEN=your_telegram_bot_token_here
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority
RENDER_EXTERNAL_URL=[https://your-app-name.onrender.com](https://your-app-name.onrender.com)
PORT=8080

```


4. **Run the bot:**
```bash
python bot.py

```



---

## 🇹🇭 เวอร์ชันภาษาไทย (Thai Version)

บอท Telegram สำหรับนักเทรดระดับโปร ระบบสามารถสแกนตลาดหุ้นทั่วโลก (อเมริกา, จีน, ฮ่องกง, ไทย และ คริปโต) อัตโนมัติ เพื่อหาจุดเข้าซื้อ/ขายที่สวยที่สุด โดยใช้การวิเคราะห์ทางเทคนิคขั้นสูง (EMA, MACD, RSI, Bollinger Bands, ATR และ Volume)

### ✨ ฟีเจอร์หลัก

* **🌍 Global Market Scanner:** สแกนหาหุ้น Top 5 สัญญาณซื้อ/ขาย จาก 5 ตลาดหลัก (TH, CN, HK, US, CRYPTO)
* **🧠 Smart Stateful Scanning:** ระบบสแกนแบบฉลาด จดจำหุ้นที่สวยไว้แล้ว และหาตัวใหม่มาเติมเฉพาะโควต้าที่แหว่งไป ทำให้สแกนรอบถัดไปรวดเร็วมาก
* **📊 Pro Chart Generation:** สร้างกราฟแท่งเทียนระดับโปร พร้อมวาดเส้นอินดิเคเตอร์, จุดเข้า (Entry), จุดทำกำไร (TP) และจุดตัดขาดทุน (SL) ให้อัตโนมัติ
* **🔔 Price Alerts & Daily Notify:** ตั้งเตือนราคาแบบกำหนดเองได้ และมีระบบสรุปภาพรวมตลาดโลกส่งให้ทุกเช้า
* **💾 Persistent Storage:** เชื่อมต่อกับฐานข้อมูล MongoDB ข้อมูลผู้ใช้และการตั้งเตือนจะไม่หายไปแม้เซิร์ฟเวอร์จะรีสตาร์ท
* **⚡ High Concurrency:** รองรับผู้ใช้งานจำนวนมากพร้อมกัน โดยไม่เกิดอาการคอขวด ด้วยระบบ `asyncio` และ `ThreadPoolExecutor`
* **🛡️ Anti-Sleep System:** มีระบบป้องกันเซิร์ฟเวอร์หลับ (Keep-alive ping) สำหรับการรันบน Render สายฟรี

### 🕹️ คำสั่งการใช้งาน (Commands)

| คำสั่ง | รายละเอียด |
| --- | --- |
| `/start` | เริ่มต้นใช้งานบอทและดูคู่มือ |
| `/signal <ชื่อหุ้น> <ตลาด>` | วิเคราะห์กราฟแบบเจาะจงพร้อมวาดรูป (เช่น `/signal CPALL SET`) |
| `/alert <ชื่อหุ้น> <ตลาด> <above/below> <ราคา>` | ตั้งเตือนราคา (เช่น `/alert BTCUSDT BINANCE below 80000`) |
| `/top_all` | ดูสรุปหุ้นกระทิง Top 3 จากทุกตลาดทั่วโลก |
| `/top_th`, `/top_us`, `/top_crypto` | ดูหุ้น Top 5 ของตลาดที่เลือก |
| `/top_sell_all` | ดูสรุปเตือนภัยหุ้นขาลงจากทุกตลาดทั่วโลก |
| `/top_on` / `/top_off` | เปิด/ปิด รับการแจ้งเตือนสรุปตลาดทุกเช้าเวลา 08:00 น. |

### 🚀 วิธีการติดตั้งและการใช้งาน

1. **โคลนโปรเจกต์:**
```bash
git clone [[https://github.com/yourusername/your-repo-name.git](https://github.com/yourusername/your-repo-name.git)](https://github.com/NatanonThunil/Trand-2.git)
cd your-repo-name

```


2. **ติดตั้งไลบรารีที่จำเป็น:**
```bash
pip install -r requirements.txt

```


3. **ตั้งค่าตัวแปรระบบ (`.env`):**
สร้างไฟล์ชื่อ `.env` และกรอกข้อมูลดังนี้:
```env
BOT_TOKEN=ใส่_token_bot_telegram_ของคุณที่นี่
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority
RENDER_EXTERNAL_URL=[https://your-app-name.onrender.com](https://your-app-name.onrender.com)
PORT=8080

```


*(หมายเหตุ: รหัสผ่าน MongoDB ต้องไม่มีอักขระพิเศษ หรือต้องถูกทำ URL Encode)*
4. **เริ่มรันบอท:**
```bash
python bot.py

```



---

<div align="center">
<i>Built with ❤️ by an Algorithmic Trader</i>
</div>

```

