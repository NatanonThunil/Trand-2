import asyncio
from datetime import time, timezone, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from guide import get_user_guide
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

# ==========================================
# 🧩 STRATEGY IMPORTS
# ==========================================
from strategy import (
    run_strategy,
    # Scanners (Buy)
    scan_top_th_symbols, scan_top_cn_symbols, scan_top_hk_symbols, scan_top_us_stock_symbols, scan_top_crypto_symbols,
    # Scanners (Sell)
    scan_top_th_sell_symbols, scan_top_cn_sell_symbols, scan_top_hk_sell_symbols, scan_top_us_stock_sell_symbols, scan_top_crypto_sell_symbols,
    # Getters (Buy)
    get_top_th_text, get_top_cn_text, get_top_hk_text, get_top_us_stock_text, get_top_crypto_text, get_global_top_text,
    # Getters (Sell)
    get_top_th_sell_text, get_top_cn_sell_text, get_top_hk_sell_text, get_top_us_stock_sell_text, get_top_crypto_sell_text, get_global_sell_text,
    run_heavy_scan_all_markets
)

from alert_store import load_alerts, save_alerts, remove_alert, format_alert_message
from tvDatafeed import TvDatafeed, Interval
import os
from dotenv import load_dotenv
from user_store import is_new_user, mark_user_seen
from top_notify_store import add_top_notify_user, remove_top_notify_user, load_top_notify_users

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ======================
# 🛠 HELPER FUNCTION (On-Demand Scan)
# ======================
async def execute_scan_command(update: Update, scan_func, get_text_func, market_name: str):
    """
    สั่งสแกนทันทีเมื่อผู้ใช้กดคำสั่ง (เช่น /top_th)
    """
    status_msg = await update.message.reply_text(f"⏳ กำลังสแกน *{market_name}* (Day) ล่าสุด... (อาจใช้เวลา 1-2 นาที)", parse_mode="Markdown")
    try:
        # ย้ายไปทำใน Thread แยก เพื่อไม่ให้บอทค้าง
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, scan_func)
        
        # ดึงผลลัพธ์
        result_text = get_text_func()
        await status_msg.edit_text(result_text, parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error Scanning {market_name}: {e}")

# ======================
# BASIC COMMANDS
# ======================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 Global error:", context.error)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_new_user(update.effective_chat.id):
        await update.message.reply_text(get_user_guide(), parse_mode="Markdown")
        mark_user_seen(update.effective_chat.id)
    else:
        await update.message.reply_text("👋 ยินดีต้อนรับกลับ\nพิมพ์ /help ดูคู่มือ", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_user_guide(), parse_mode="Markdown")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ ใช้คำสั่ง:\n/signal BTCUSDT BINANCE")
        return

    symbol = context.args[0].upper()
    exchange = context.args[1].upper()
    await update.message.reply_text(f"⏳ กำลังวิเคราะห์ {symbol} ({exchange})...")

    chart_path = None
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_strategy, symbol, exchange)
        await update.message.reply_text(result["text"], parse_mode="Markdown")

        chart_path = result.get("chart")
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, "rb") as photo:
                await update.message.reply_photo(photo)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        if chart_path and os.path.exists(chart_path):
            try: os.remove(chart_path)
            except: pass

async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4:
        return await update.message.reply_text("❌ ตัวอย่าง: /alert BTCUSDT BINANCE above 50000")
    
    symbol, exchange, direction, price = context.args
    try: price = float(price)
    except: return await update.message.reply_text("❌ ราคาไม่ถูกต้อง")

    alerts = load_alerts()
    alerts.append({
        "chat_id": update.effective_chat.id,
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "direction": direction.lower(),
        "price": price
    })
    save_alerts(alerts)
    await update.message.reply_text(f"🔔 ตั้งเตือน {symbol} {direction} {price} สำเร็จ")

async def auto_check_alerts(context: ContextTypes.DEFAULT_TYPE):
    tv = TvDatafeed()
    alerts = load_alerts()
    remaining = alerts.copy()
    for alert in alerts:
        try:
            df = tv.get_hist(symbol=alert["symbol"], exchange=alert["exchange"], interval=Interval.in_1_minute, n_bars=1)
            if df is None: continue
            cur = df.iloc[-1]["close"]
            hit = (alert["direction"]=="above" and cur>=alert["price"]) or (alert["direction"]=="below" and cur<=alert["price"])
            if hit:
                await context.bot.send_message(alert["chat_id"], format_alert_message(alert, cur), parse_mode="Markdown")
                remaining = remove_alert(remaining, alert)
        except: pass
    save_alerts(remaining)

# ======================
# 🏆 TOP COMMANDS (Buy)
# ======================
async def top_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_crypto_symbols, get_top_crypto_text, "Crypto Buy")
async def top_th(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_th_symbols, get_top_th_text, "หุ้นไทย Buy")
async def top_cn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_cn_symbols, get_top_cn_text, "หุ้นจีน Buy")
async def top_hk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_hk_symbols, get_top_hk_text, "หุ้นฮ่องกง Buy")
async def top_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_us_stock_symbols, get_top_us_stock_text, "หุ้น US Buy")
async def top_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_global_top_text()
    if "กำลังสแกน" in text:
        # ถ้าไม่มี Cache ให้ผู้ใช้รอรอบ Auto Scan จะดีกว่า เพื่อไม่ให้รอนานเกินไป
        await update.message.reply_text("⏳ ข้อมูล Global ยังไม่พร้อม รอระบบอัปเดตสักครู่...", parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

# ======================
# 🔴 TOP COMMANDS (Sell)
# ======================
async def top_sell_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_crypto_sell_symbols, get_top_crypto_sell_text, "Crypto Sell")
async def top_sell_th(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_th_sell_symbols, get_top_th_sell_text, "หุ้นไทย Sell")
async def top_sell_cn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_cn_sell_symbols, get_top_cn_sell_text, "หุ้นจีน Sell")
async def top_sell_hk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_hk_sell_symbols, get_top_hk_sell_text, "หุ้นฮ่องกง Sell")
async def top_sell_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_scan_command(update, scan_top_us_stock_sell_symbols, get_top_us_stock_sell_text, "หุ้น US Sell")
async def top_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_global_sell_text()
    if "กำลังสแกน" in text:
        await update.message.reply_text("⏳ ข้อมูล Global Sell ยังไม่พร้อม รอระบบอัปเดตสักครู่...", parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

# ======================
# 🔔 NOTIFICATIONS
# ======================
async def top_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_top_notify_user(update.effective_chat.id)
    await update.message.reply_text("🔔 เปิดแจ้งเตือนรายวัน (09:00)")
async def top_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remove_top_notify_user(update.effective_chat.id)
    await update.message.reply_text("🔕 ปิดแจ้งเตือนแล้ว")

async def send_daily_top(context: ContextTypes.DEFAULT_TYPE):
    users = load_top_notify_users()
    if not users: return
    
    parts = ["🌅 *DAILY GLOBAL MARKET* 🌅\n_(คัดหุ้น 200 ตัวแรก/ตลาด จากราคาปิดเมื่อวาน)_"]
    
    buy_txt = get_global_top_text()
    if "กำลังสแกน" not in buy_txt: parts.append(buy_txt)
    
    sell_txt = get_global_sell_text()
    if "กำลังสแกน" not in sell_txt: parts.append(sell_txt)
    
    msg = "\n\n━━━━━━━━━━━━━━\n\n".join(parts)
    for uid in users:
        try: await context.bot.send_message(uid, msg, parse_mode="Markdown")
        except: pass

# ======================
# ⚙️ BACKGROUND JOB (HEAVY SCAN)
# ======================
def run_all_scans_sync():
    """
    ฟังก์ชันนี้จะรันใน Thread แยก
    ทำหน้าที่สแกนทุกตลาด (Buy & Sell) โดยใช้ Logic ใน strategy.py
    (ซึ่งตั้งค่าเป็น Daily Timeframe และ limit=200 ตัว)
    """
    print("🌅 [Job] Starting Daily Heavy Scan (ALL MARKETS)...")
    
    # === BUY SCANS ===
    try:
        print("   Checking Crypto Buy...")
        scan_top_crypto_symbols()
    except Exception as e: print(f"   x Crypto Buy Error: {e}")

    try:
        print("   Checking TH Buy...")
        scan_top_th_symbols()
    except Exception as e: print(f"   x TH Buy Error: {e}")

    try:
        print("   Checking CN Buy...")
        scan_top_cn_symbols()
    except Exception as e: print(f"   x CN Buy Error: {e}")

    try:
        print("   Checking HK Buy...")
        scan_top_hk_symbols()
    except Exception as e: print(f"   x HK Buy Error: {e}")

    try:
        print("   Checking US Buy...")
        scan_top_us_stock_symbols()
    except Exception as e: print(f"   x US Buy Error: {e}")

    # === SELL SCANS ===
    try:
        print("   Checking Crypto Sell...")
        scan_top_crypto_sell_symbols()
    except Exception as e: print(f"   x Crypto Sell Error: {e}")

    try:
        print("   Checking TH Sell...")
        scan_top_th_sell_symbols()
    except Exception as e: print(f"   x TH Sell Error: {e}")

    try:
        print("   Checking CN Sell...")
        scan_top_cn_sell_symbols()
    except Exception as e: print(f"   x CN Sell Error: {e}")

    try:
        print("   Checking HK Sell...")
        scan_top_hk_sell_symbols()
    except Exception as e: print(f"   x HK Sell Error: {e}")

    try:
        print("   Checking US Sell...")
        scan_top_us_stock_sell_symbols()
    except Exception as e: print(f"   x US Sell Error: {e}")

    print("✅ [Job] All Market Scans Complete!")

async def scan_market_job(context: ContextTypes.DEFAULT_TYPE):
    # Offload to thread to prevent blocking
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_heavy_scan_all_markets)

# ======================
# 🌐 DUMMY WEB SERVER (เพื่อหลอก Choreo ว่าเราคือเว็บ)
# ======================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running OK!")

def run_web_server():
    # Choreo มักจะส่ง PORT มาใน Environment Variable (ค่า default คือ 8080)
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌍 Dummy Server running on port {port}")
    server.serve_forever()

# ======================
# MAIN
# ======================
def main():

    threading.Thread(target=run_web_server, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("alert", alert))
    
    # Top Handlers
    app.add_handler(CommandHandler("top", top_crypto))
    app.add_handler(CommandHandler("top_th", top_th))
    app.add_handler(CommandHandler("top_cn", top_cn))
    app.add_handler(CommandHandler("top_hk", top_hk))
    app.add_handler(CommandHandler("top_us", top_us))
    app.add_handler(CommandHandler("top_all", top_global))
    
    app.add_handler(CommandHandler("top_sell", top_sell_crypto))
    app.add_handler(CommandHandler("top_sell_th", top_sell_th))
    app.add_handler(CommandHandler("top_sell_cn", top_sell_cn))
    app.add_handler(CommandHandler("top_sell_hk", top_sell_hk))
    app.add_handler(CommandHandler("top_sell_us", top_sell_us))
    app.add_handler(CommandHandler("top_sell_all", top_sell_all))
    
    app.add_handler(CommandHandler("top_on", top_on))
    app.add_handler(CommandHandler("top_off", top_off))
    app.add_error_handler(error_handler)

    # Job Queue
    TH_TZ = timezone(timedelta(hours=7))

    # 1. Alert (Check every 2 mins)
    app.job_queue.run_repeating(auto_check_alerts, interval=120, first=10, name="auto_alert")
    
    # 2. Daily Scan (Heavy Scan) - ตั้งไว้ตี 5 ครึ่ง (05:30)
    # เพื่อให้ตลาด US ปิดสนิทแล้ว และมีเวลาสแกนให้เสร็จก่อน 9 โมง
    app.job_queue.run_daily(
        scan_market_job, 
        time=time(hour=5, minute=30, tzinfo=TH_TZ), 
        name="daily_heavy_scan"
    )
    
    # 3. Daily Notify - แจ้งเตือนตอน 9 โมงเช้า (09:00)
    # ข้อมูลจะพร้อมเพราะเราสแกนเสร็จตั้งแต่เช้ามืดแล้ว
    app.job_queue.run_daily(
        send_daily_top, 
        time=time(hour=9, minute=0, tzinfo=TH_TZ), 
        name="daily_notify"
    )

    print("🤖 Bot Started | Daily Scan @ 08:30 | Notify @ 09:00")
    app.run_polling()

if __name__ == "__main__":
    main()