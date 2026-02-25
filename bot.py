import asyncio
import logging
import os
import threading
import time
import requests
from datetime import time as dt_time, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", None) 

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING) 

logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.critical("❌ ไม่พบ BOT_TOKEN! ตรวจสอบไฟล์ .env")
    exit(1)

# ✅ สร้าง Thread Pool สำหรับทำงานหนักคู่ขนานกัน (20 คนพร้อมกันสบายๆ)
executor = ThreadPoolExecutor(max_workers=20)

# ✅ Lock ป้องกัน Matplotlib พัง (ใช้เฉพาะตอนวาดกราฟ /signal)
signal_lock = asyncio.Lock()

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
        scan_top_th_symbols, scan_top_cn_symbols, scan_top_hk_symbols, scan_top_us_stock_symbols, scan_top_crypto_symbols,
        scan_top_th_sell_symbols, scan_top_cn_sell_symbols, scan_top_hk_sell_symbols, scan_top_us_stock_sell_symbols, scan_top_crypto_sell_symbols,
        get_top_th_text, get_top_cn_text, get_top_hk_text, get_top_us_stock_text, get_top_crypto_text, get_global_top_text,
        get_top_th_sell_text, get_top_cn_sell_text, get_top_hk_sell_text, get_top_us_stock_sell_text, get_top_crypto_sell_text, get_global_sell_text,
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
        self.wfile.write(b"Bot is active and awake!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 8080)) 
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        logger.info(f"🌍 Web Server running on port {port}")
        server.serve_forever()
    except OSError as e:
        logger.warning(f"⚠️ Web Server Error: {e}")

# ======================
# 🔔 KEEP-ALIVE PING 
# ======================
def keep_alive_ping():
    port = os.environ.get("PORT", 8080)
    url = RENDER_EXTERNAL_URL
    
    if not url:
        logger.error("🚨 WARNING: ไม่พบ RENDER_EXTERNAL_URL ใน Env Variables!")
        url = f"http://127.0.0.1:{port}"
    
    time.sleep(15)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    while True:
        try:
            requests.get(url, headers=headers, timeout=10)
        except Exception:
            pass
        time.sleep(300)

# ======================
# 🎨 UI HELPERS
# ======================
def make_progress_bar(percent, length=12):
    filled_length = int(length * percent // 100)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar

# ======================
# 🛠 BACKGROUND TASKS (แก้ไขปัญหาค้าง 100%)
# ======================
async def _scan_bg_task(chat_id: int, bot, scan_func, get_text_func, market_name: str):
    """ฟังก์ชันที่จะถูกโยนไปรันเบื้องหลัง ทำให้บอทไม่ค้าง"""
    start_msg_text = f"📡 *INITIALIZING SCAN...*\n🔍 Target: *{market_name}*\n\n`[░░░░░░░░░░░░] 0%`"
    
    # ส่งข้อความไปก่อน แล้วเก็บ Message ID ไว้แก้ไขทีหลัง
    status_msg = await bot.send_message(chat_id=chat_id, text=start_msg_text, parse_mode="Markdown")
    
    last_update_time = time.time()
    loop = asyncio.get_running_loop()

    # Callback อัปเดต %
    def progress_callback(current, total):
        nonlocal last_update_time
        now = time.time()
        
        # อัปเดตระหว่างทาง (ทุก 3 วิ)
        if now - last_update_time > 3.0 and current < total:
            percent = int((current / total) * 100)
            bar = make_progress_bar(percent, length=12) 
            text = (
                f"📡 *SCANNING MARKET...*\n"
                f"🎯 Target: *{market_name}*\n"
                f"🔎 Checked: {current}/{total}\n\n"
                f"`[{bar}] {percent}%`\n"
                f"⏳ _Please wait..._"
            )
            try:
                asyncio.run_coroutine_threadsafe(
                    bot.edit_message_text(text=text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown"), 
                    loop
                )
            except Exception: pass
            last_update_time = time.time()

    try:
        # 🚀 1. สั่งรันสแกนเบื้องหลังให้เสร็จสมบูรณ์
        
        await loop.run_in_executor(executor, lambda: scan_func(callback=progress_callback))
        
        # 🚀 2. เมื่อหลุดจากบรรทัดบนแปลว่า "เสร็จแล้ว 100%" แน่นอน
        # ให้ดึงข้อความผลลัพธ์มา Edit ทับทันที (ไม่ต้องสน Callback ตอน 100% แล้ว)
        result_text = get_text_func()
        
        await bot.edit_message_text(
            text=result_text, 
            chat_id=chat_id, 
            message_id=status_msg.message_id, 
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Scan Error ({market_name}): {e}")
        try:
            await bot.edit_message_text(
                text=f"❌ *SYSTEM ERROR*\n`{e}`", 
                chat_id=chat_id, 
                message_id=status_msg.message_id, 
                parse_mode="Markdown"
            )
        except: pass

async def _signal_bg_task(chat_id: int, bot, symbol: str, exchange: str):
    """ฟังก์ชันวาดกราฟเบื้องหลัง"""
    msg = await bot.send_message(chat_id=chat_id, text="⏳ Analyzing Data & Generating Chart...")
    try:
        loop = asyncio.get_running_loop()
        
        # คิวการสร้างกราฟ (วาดทีละรูป ป้องกัน Matplotlib พัง)
        async with signal_lock:
            res = await loop.run_in_executor(executor, run_strategy, symbol, exchange)
        
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        await bot.send_message(chat_id=chat_id, text=res["text"], parse_mode="Markdown")
        
        if res["chart"] and os.path.exists(res["chart"]):
            with open(res["chart"], "rb") as p: 
                await bot.send_photo(chat_id=chat_id, photo=p)
            os.remove(res["chart"])
            
    except Exception as e: 
        await bot.edit_message_text(text=f"❌ Error: {e}", chat_id=chat_id, message_id=msg.message_id)

# ======================
# 🎮 COMMAND HANDLERS (✅ เปลี่ยนให้ลื่นไหล 100%)
# ======================
async def execute_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE, scan_func, get_text_func, market_name: str):
    # 🎯 ใช้ create_task เพื่อ "สั่งงานแล้วปล่อยเลย" บอทจะว่างรับคนต่อไปทันที
    asyncio.create_task(_scan_bg_task(update.effective_chat.id, context.bot, scan_func, get_text_func, market_name))

async def signal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not c.args or len(c.args)<2: return await u.message.reply_text("Usage: /signal BTCUSDT BINANCE")
    # 🎯 ใช้ create_task วาดกราฟเบื้องหลัง 
    asyncio.create_task(_signal_bg_task(u.effective_chat.id, c.bot, c.args[0].upper(), c.args[1].upper()))

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    chat_id = u.effective_chat.id
    
    # ถ้าเป็นผู้ใช้งานใหม่ (ไม่เคยทักบอทมาก่อน)
    if is_new_user(chat_id):
        mark_user_seen(chat_id)
        guide_text = get_user_guide()
        try:
            # ลองส่งแบบจัดรูปแบบ Markdown ก่อน
            await u.message.reply_text(guide_text, parse_mode="Markdown")
        except Exception as e:
            # ถ้ารูปแบบพัง (ลืมปิดแท็ก) ให้ส่งเป็นข้อความธรรมดาแทน บอทจะได้ไม่ดับ
            logger.error(f"Markdown Parse Error in Start: {e}")
            await u.message.reply_text(guide_text)
    
    # ถ้าเป็นผู้ใช้งานเก่าที่เคยกด Start ไปแล้ว
    else:
        try:
            await u.message.reply_text(
                "👋 ยินดีต้อนรับกลับมาครับ!\n\n"
                "พิมพ์ /help เพื่อดูคู่มือการใช้งานอีกครั้ง\n"
                "หรือพิมพ์คำสั่งสแกนกราฟได้เลย (เช่น `/top_th`)", 
                parse_mode="Markdown"
            )
        except:
            await u.message.reply_text("👋 ยินดีต้อนรับกลับมาครับ!\n\nพิมพ์ /help เพื่อดูคู่มือการใช้งานอีกครั้ง\nหรือพิมพ์คำสั่งสแกนกราฟได้เลย (เช่น /top_th)")
        
async def help_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE):
    guide_text = get_user_guide()
    try:
        await u.message.reply_text(guide_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Markdown Parse Error in Help: {e}")
        await u.message.reply_text(guide_text) # ส่งแบบธรรมดาถ้า Markdown พัง

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
async def top_crypto(u, c): await execute_scan_command(u, c, scan_top_crypto_symbols, get_top_crypto_text, "Crypto Buy")
async def top_th(u, c): await execute_scan_command(u, c, scan_top_th_symbols, get_top_th_text, "TH Buy")
async def top_cn(u, c): await execute_scan_command(u, c, scan_top_cn_symbols, get_top_cn_text, "CN Buy")
async def top_hk(u, c): await execute_scan_command(u, c, scan_top_hk_symbols, get_top_hk_text, "HK Buy")
async def top_us(u, c): await execute_scan_command(u, c, scan_top_us_stock_symbols, get_top_us_stock_text, "US Buy")
async def top_global(u, c): 
    text = get_global_top_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global กำลังรอรอบสแกน...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_sell_crypto(u, c): await execute_scan_command(u, c, scan_top_crypto_sell_symbols, get_top_crypto_sell_text, "Crypto Sell")
async def top_sell_th(u, c): await execute_scan_command(u, c, scan_top_th_sell_symbols, get_top_th_sell_text, "TH Sell")
async def top_sell_cn(u, c): await execute_scan_command(u, c, scan_top_cn_sell_symbols, get_top_cn_sell_text, "CN Sell")
async def top_sell_hk(u, c): await execute_scan_command(u, c, scan_top_hk_sell_symbols, get_top_hk_sell_text, "HK Sell")
async def top_sell_us(u, c): await execute_scan_command(u, c, scan_top_us_stock_sell_symbols, get_top_us_stock_sell_text, "US Sell")
async def top_sell_all(u, c): 
    text = get_global_sell_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global Sell กำลังรอรอบสแกน...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_on(u, c): add_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔔 On")
async def top_off(u, c): remove_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔕 Off")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"🔥 Update {update} caused error: {context.error}")

# ======================
# 🕒 SCHEDULER JOBS
# ======================
async def job_scan_asia(ctx): await asyncio.get_running_loop().run_in_executor(executor, run_scan_asia_market)
async def job_scan_th(ctx): await asyncio.get_running_loop().run_in_executor(executor, run_scan_th_market)
async def job_scan_us(ctx): await asyncio.get_running_loop().run_in_executor(executor, run_scan_us_market)

async def job_notify(ctx):
    """ฟังก์ชันแจ้งเตือนตอนเช้า (ปรับปรุงใหม่)"""
    logger.info("🌅 กำลังเริ่มส่ง Daily Notification...")
    
    users = load_top_notify_users()
    if not users:
        logger.warning("⚠️ ไม่มีรายชื่อ User ในระบบแจ้งเตือน (ไม่มีใครกด /top_on)")
        return

    # ดึงข้อความมาเตรียมไว้รอบเดียว จะได้ไม่ดึงซ้ำๆ ให้หนักเครื่อง
    msg = f"🌅 *DAILY GLOBAL UPDATE*\n\n{get_global_top_text()}\n\n{get_global_sell_text()}"
    
    success_count = 0
    for chat_id in users:
        try:
            # ใช้วิธีส่งแบบปกติ ไม่ต้องครอบด้วย run_in_executor เพราะมันเป็น Async อยู่แล้ว
            await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            success_count += 1
            await asyncio.sleep(0.5) # พักเบรกนิดหน่อย กันโดน Telegram มองว่าเราสแปมข้อความ
        except Exception as e:
            logger.error(f"❌ ส่งแจ้งเตือนให้ {chat_id} ไม่สำเร็จ: {e}")
            
    logger.info(f"✅ ส่ง Daily Notification สำเร็จ {success_count}/{len(users)} คน")

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
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    # เปิดใช้งานการรับคำสั่งคู่ขนานแบบเต็มสูบ
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("alert", alert))
    
    app.add_handler(CommandHandler("top", top_crypto)); app.add_handler(CommandHandler("top_th", top_th))
    app.add_handler(CommandHandler("top_cn", top_cn)); app.add_handler(CommandHandler("top_hk", top_hk))
    app.add_handler(CommandHandler("top_us", top_us)); app.add_handler(CommandHandler("top_all", top_global))
    
    app.add_handler(CommandHandler("top_sell", top_crypto)); app.add_handler(CommandHandler("top_sell_th", top_sell_th))
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

    logger.info("🤖 Bot Started Ready!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.critical(f"🔥 CRITICAL ERROR: {e}")
            logger.info("🔄 Restarting bot in 10 seconds...")
            time.sleep(10)
        except KeyboardInterrupt:
            print("🛑 Bot stopped by user")
            break