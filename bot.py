import asyncio
import logging
import os
import threading
import time
from datetime import time as dt_time, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# ตั้งค่า Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.critical("❌ ไม่พบ BOT_TOKEN! ตรวจสอบไฟล์ .env")
    exit(1)

# ==========================================
# 🧩 IMPORTS
# ==========================================
try:
    try:
        from guide import get_user_guide
    except ImportError:
        def get_user_guide(): return "❌ ไม่พบไฟล์คู่มือ (guide.py)"

    from strategy import (
        run_strategy,
        # Scanners
        scan_top_th_symbols, scan_top_cn_symbols, scan_top_hk_symbols, scan_top_us_stock_symbols, scan_top_crypto_symbols,
        scan_top_th_sell_symbols, scan_top_cn_sell_symbols, scan_top_hk_sell_symbols, scan_top_us_stock_sell_symbols, scan_top_crypto_sell_symbols,
        # Getters
        get_top_th_text, get_top_cn_text, get_top_hk_text, get_top_us_stock_text, get_top_crypto_text, get_global_top_text,
        get_top_th_sell_text, get_top_cn_sell_text, get_top_hk_sell_text, get_top_us_stock_sell_text, get_top_crypto_sell_text, get_global_sell_text,
        # Heavy Jobs
        run_scan_asia_market, run_scan_th_market, run_scan_us_market
    )
    
    from alert_store import load_alerts, save_alerts, remove_alert, format_alert_message
    from user_store import is_new_user, mark_user_seen
    from top_notify_store import add_top_notify_user, remove_top_notify_user, load_top_notify_users
    from tvDatafeed import TvDatafeed, Interval

except ImportError as e:
    logger.critical(f"❌ IMPORT ERROR: {e}")
    exit(1)

# ======================
# 🌐 DUMMY SERVER
# ======================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is active!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        logger.info(f"🌍 Dummy Server running on port {port}")
        server.serve_forever()
    except OSError as e:
        logger.warning(f"⚠️ Web Server Start Failed: {e}")

# ======================
# 🛠 HELPER (SCAN + PROGRESS) -> แก้จุดนี้เพื่อให้ Non-blocking
# ======================
async def execute_scan_command(update: Update, scan_func, get_text_func, market_name: str):
    # ส่งข้อความเริ่มต้นไปก่อน
    status_msg = await update.message.reply_text(f"⏳ เริ่มสแกน *{market_name}*... 0%", parse_mode="Markdown")
    
    # ตัวแปรสำหรับคุมความถี่การอัปเดต (Telegram จำกัดการ Edit)
    last_update_time = 0
    loop = asyncio.get_running_loop()

    # ฟังก์ชัน Callback ที่จะถูกเรียกจาก strategy.py ใน Thread แยก
    def progress_callback(current, total):
        nonlocal last_update_time
        # อัปเดตทุกๆ 3 วินาที หรือเมื่อเสร็จ
        if time.time() - last_update_time > 3 or current == total:
            percent = int((current / total) * 100)
            text = f"⏳ กำลังสแกน *{market_name}*... {percent}% ({current}/{total})"
            try:
                # สั่งให้ Event Loop ของบอททำงานอัปเดตข้อความ (Thread-safe)
                asyncio.run_coroutine_threadsafe(
                    status_msg.edit_text(text, parse_mode="Markdown"), 
                    loop
                )
            except: pass
            last_update_time = time.time()

    try:
        # ✅ รันฟังก์ชันสแกนใน Thread แยก (Executor) เพื่อให้ Main Loop ไม่ค้าง
        # บอทจะยังรับคำสั่งอื่นได้ระหว่างบรรทัดนี้ทำงาน
        await loop.run_in_executor(None, lambda: scan_func(callback=progress_callback))
        
        # เมื่อเสร็จแล้ว ดึงข้อความสรุปมาแสดง
        result_text = get_text_func()
        await status_msg.edit_text(result_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Scan Error ({market_name}): {e}")
        await status_msg.edit_text(f"❌ เกิดข้อผิดพลาด: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"🔥 Update {update} caused error: {context.error}")

# ======================
# 🎮 COMMANDS
# ======================
async def start(u, c): await u.message.reply_text(get_user_guide(), parse_mode="Markdown")
async def help_cmd(u, c): await u.message.reply_text(get_user_guide(), parse_mode="Markdown")

async def signal(u, c):
    if not c.args or len(c.args)<2: return await u.message.reply_text("Usage: /signal BTCUSDT BINANCE")
    msg = await u.message.reply_text("Analyzing...")
    try:
        res = await asyncio.get_running_loop().run_in_executor(None, run_strategy, c.args[0].upper(), c.args[1].upper())
        await msg.delete()
        await u.message.reply_text(res["text"], parse_mode="Markdown")
        if res["chart"] and os.path.exists(res["chart"]):
            with open(res["chart"], "rb") as p: await u.message.reply_photo(p)
            os.remove(res["chart"])
    except Exception as e: await u.message.reply_text(f"Error: {e}")

async def alert(u, c):
    if not c.args or len(c.args)!=4: return await u.message.reply_text("Ex: /alert BTCUSDT BINANCE above 50000")
    try:
        p = float(c.args[3])
        al = load_alerts()
        al.append({"chat_id":u.effective_chat.id, "symbol":c.args[0].upper(), "exchange":c.args[1].upper(), "direction":c.args[2], "price":p})
        save_alerts(al)
        await u.message.reply_text("✅ Alert Saved!")
    except: await u.message.reply_text("❌ Error saving alert")

# Wrappers
async def top_crypto(u, c): await execute_scan_command(u, scan_top_crypto_symbols, get_top_crypto_text, "Crypto Buy")
async def top_th(u, c): await execute_scan_command(u, scan_top_th_symbols, get_top_th_text, "TH Buy")
async def top_cn(u, c): await execute_scan_command(u, scan_top_cn_symbols, get_top_cn_text, "CN Buy")
async def top_hk(u, c): await execute_scan_command(u, scan_top_hk_symbols, get_top_hk_text, "HK Buy")
async def top_us(u, c): await execute_scan_command(u, scan_top_us_stock_symbols, get_top_us_stock_text, "US Buy")
async def top_global(u, c): 
    text = get_global_top_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global กำลังรอรอบสแกน...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_sell_crypto(u, c): await execute_scan_command(u, scan_top_crypto_sell_symbols, get_top_crypto_sell_text, "Crypto Sell")
async def top_sell_th(u, c): await execute_scan_command(u, scan_top_th_sell_symbols, get_top_th_sell_text, "TH Sell")
async def top_sell_cn(u, c): await execute_scan_command(u, scan_top_cn_sell_symbols, get_top_cn_sell_text, "CN Sell")
async def top_sell_hk(u, c): await execute_scan_command(u, scan_top_hk_sell_symbols, get_top_hk_sell_text, "HK Sell")
async def top_sell_us(u, c): await execute_scan_command(u, scan_top_us_stock_sell_symbols, get_top_us_stock_sell_text, "US Sell")
async def top_sell_all(u, c): 
    text = get_global_sell_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global Sell กำลังรอรอบสแกน...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_on(u, c): add_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔔 On")
async def top_off(u, c): remove_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔕 Off")

# Jobs (Scheduled)
async def job_scan_asia(ctx): await asyncio.get_running_loop().run_in_executor(None, run_scan_asia_market)
async def job_scan_th(ctx): await asyncio.get_running_loop().run_in_executor(None, run_scan_th_market)
async def job_scan_us(ctx): await asyncio.get_running_loop().run_in_executor(None, run_scan_us_market)
async def job_notify(ctx):
    u = load_top_notify_users(); msg = f"🌅 *DAILY*\n\n{get_global_top_text()}\n\n{get_global_sell_text()}"
    for i in u:
        try: await ctx.bot.send_message(i, msg, parse_mode="Markdown")
        except: pass
async def job_check_alerts(ctx):
    tv=TvDatafeed(); al=load_alerts(); rem=al.copy()
    for a in al:
        try:
            df=tv.get_hist(a["symbol"], a["exchange"], Interval.in_1_minute, 1)
            if df is not None:
                c=df.iloc[-1]["close"]; h=(a["direction"]=="above" and c>=a["price"]) or (a["direction"]=="below" and c<=a["price"])
                if h: await ctx.bot.send_message(a["chat_id"], format_alert_message(a, c), parse_mode="Markdown"); rem.remove(a)
        except: pass
    if len(rem)!=len(al): save_alerts(rem)

# ======================
# MAIN
# ======================
def main():
    threading.Thread(target=run_web_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("alert", alert))
    
    app.add_handler(CommandHandler("top", top_crypto)); app.add_handler(CommandHandler("top_th", top_th))
    app.add_handler(CommandHandler("top_cn", top_cn)); app.add_handler(CommandHandler("top_hk", top_hk))
    app.add_handler(CommandHandler("top_us", top_us)); app.add_handler(CommandHandler("top_all", top_global))
    
    app.add_handler(CommandHandler("top_sell", top_sell_crypto)); app.add_handler(CommandHandler("top_sell_th", top_sell_th))
    app.add_handler(CommandHandler("top_sell_cn", top_sell_cn)); app.add_handler(CommandHandler("top_sell_hk", top_sell_hk))
    app.add_handler(CommandHandler("top_sell_us", top_sell_us)); app.add_handler(CommandHandler("top_sell_all", top_sell_all))
    
    app.add_handler(CommandHandler("top_on", top_on)); app.add_handler(CommandHandler("top_off", top_off))
    app.add_error_handler(error_handler)

    TH_TZ = timezone(timedelta(hours=7)); jq = app.job_queue
    jq.run_daily(job_scan_asia, time=dt_time(16,30, tzinfo=TH_TZ))
    jq.run_daily(job_scan_th, time=dt_time(17,30, tzinfo=TH_TZ))
    jq.run_daily(job_scan_us, time=dt_time(5,0, tzinfo=TH_TZ))
    jq.run_daily(job_notify, time=dt_time(8,0, tzinfo=TH_TZ))
    jq.run_repeating(job_check_alerts, interval=120, first=10)

    logger.info("🤖 Bot Started")
    app.run_polling()

if __name__ == "__main__":
    main()