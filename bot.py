import asyncio
import logging
import os
import threading
from datetime import time, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket # เพิ่ม import socket

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
        scan_top_th_symbols, scan_top_cn_symbols, scan_top_hk_symbols, scan_top_us_stock_symbols, scan_top_crypto_symbols,
        scan_top_th_sell_symbols, scan_top_cn_sell_symbols, scan_top_hk_sell_symbols, scan_top_us_stock_sell_symbols, scan_top_crypto_sell_symbols,
        get_top_th_text, get_top_cn_text, get_top_hk_text, get_top_us_stock_text, get_top_crypto_text, get_global_top_text,
        get_top_th_sell_text, get_top_cn_sell_text, get_top_hk_sell_text, get_top_us_stock_sell_text, get_top_crypto_sell_text, get_global_sell_text,
        run_heavy_scan_all_markets
    )
    
    from alert_store import load_alerts, save_alerts, remove_alert, format_alert_message
    from user_store import is_new_user, mark_user_seen
    from top_notify_store import add_top_notify_user, remove_top_notify_user, load_top_notify_users
    from tvDatafeed import TvDatafeed, Interval

except ImportError as e:
    logger.critical(f"❌ IMPORT ERROR: {e}")
    exit(1)

# ======================
# 🌐 DUMMY SERVER (แบบปลอดภัย รันได้ทั้ง Windows/Cloud)
# ======================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is active!")

def run_web_server():
    # ถ้ามี ENV PORT (บน Cloud) ให้ใช้ค่าบั้น ถ้าไม่มี (บนคอม) ให้ลอง 8080 หรือสุ่ม
    port = int(os.environ.get("PORT", 8080))
    
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        logger.info(f"🌍 Dummy Server running on port {port}")
        server.serve_forever()
    except OSError as e:
        # ถ้า Port ชน (WinError 10013) ให้ข้ามไปเลย ไม่ต้อง Crash
        logger.warning(f"⚠️ Web Server Start Failed (ไม่ส่งผลต่อบอท): {e}")

# ======================
# 🛠 HELPER FUNCTIONS
# ======================
async def execute_scan_command(update: Update, scan_func, get_text_func, market_name: str):
    msg = await update.message.reply_text(f"⏳ กำลังสแกน *{market_name}*...", parse_mode="Markdown")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, scan_func)
        result = get_text_func()
        await msg.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Scan Error ({market_name}): {e}")
        await msg.edit_text(f"❌ เกิดข้อผิดพลาด: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"🔥 Update {update} caused error: {context.error}")

# ======================
# 🎮 BOT COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if is_new_user(update.effective_chat.id):
            await update.message.reply_text(get_user_guide(), parse_mode="Markdown")
            mark_user_seen(update.effective_chat.id)
        else:
            await update.message.reply_text("👋 ยินดีต้อนรับกลับ\nพิมพ์ /help ดูคู่มือ", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Start Error: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_user_guide(), parse_mode="Markdown")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ ใช้คำสั่งผิด\nตัวอย่าง: `/signal BTCUSDT BINANCE`", parse_mode="Markdown")
        return

    symbol = context.args[0].upper()
    exchange = context.args[1].upper()
    status_msg = await update.message.reply_text(f"⏳ กำลังวิเคราะห์ {symbol}...")

    chart_path = None
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_strategy, symbol, exchange)
        
        await status_msg.delete()
        await update.message.reply_text(result["text"], parse_mode="Markdown")

        chart_path = result.get("chart")
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, "rb") as photo:
                await update.message.reply_photo(photo)
    
    except ValueError as ve:
        # จับ Error เฉพาะเรื่อง float ที่คุณเจอ
        logger.error(f"Signal Value Error: {ve}")
        await update.message.reply_text(f"❌ ข้อมูลกราฟผิดพลาด (TvDatafeed คืนค่าแปลกๆ)\nError: {ve}")
        
    except Exception as e:
        logger.error(f"Signal Error: {e}")
        await update.message.reply_text(f"❌ เกิดข้อผิดพลาด: {e}")
    finally:
        if chart_path and os.path.exists(chart_path):
            try: os.remove(chart_path)
            except: pass

async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 4:
        return await update.message.reply_text("❌ ตัวอย่าง: `/alert BTCUSDT BINANCE above 50000`", parse_mode="Markdown")
    
    try:
        symbol, exchange, direction, price = context.args
        price = float(price)
        
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
    except ValueError:
        await update.message.reply_text("❌ ราคาต้องเป็นตัวเลข")
    except Exception as e:
        logger.error(f"Alert Error: {e}")
        await update.message.reply_text("❌ เกิดข้อผิดพลาดในการบันทึก")

async def auto_check_alerts(context: ContextTypes.DEFAULT_TYPE):
    alerts = load_alerts()
    if not alerts: return

    tv = TvDatafeed()
    remaining = alerts.copy()
    
    for alert in alerts:
        try:
            df = tv.get_hist(symbol=alert["symbol"], exchange=alert["exchange"], interval=Interval.in_1_minute, n_bars=1)
            if df is None or df.empty: continue
            
            cur = df.iloc[-1]["close"]
            hit = (alert["direction"]=="above" and cur>=alert["price"]) or \
                  (alert["direction"]=="below" and cur<=alert["price"])
            
            if hit:
                await context.bot.send_message(alert["chat_id"], format_alert_message(alert, cur), parse_mode="Markdown")
                remaining = remove_alert(remaining, alert)
        except Exception as e:
            logger.error(f"Check Alert Error ({alert['symbol']}): {e}")
    
    if len(remaining) != len(alerts):
        save_alerts(remaining)

# ======================
# WRAPPERS & JOBS
# ======================
async def top_crypto(u, c): await execute_scan_command(u, scan_top_crypto_symbols, get_top_crypto_text, "Crypto Buy")
async def top_th(u, c): await execute_scan_command(u, scan_top_th_symbols, get_top_th_text, "TH Buy")
async def top_cn(u, c): await execute_scan_command(u, scan_top_cn_symbols, get_top_cn_text, "CN Buy")
async def top_hk(u, c): await execute_scan_command(u, scan_top_hk_symbols, get_top_hk_text, "HK Buy")
async def top_us(u, c): await execute_scan_command(u, scan_top_us_stock_symbols, get_top_us_stock_text, "US Buy")
async def top_global(u, c): 
    text = get_global_top_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global กำลังอัปเดต...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_sell_crypto(u, c): await execute_scan_command(u, scan_top_crypto_sell_symbols, get_top_crypto_sell_text, "Crypto Sell")
async def top_sell_th(u, c): await execute_scan_command(u, scan_top_th_sell_symbols, get_top_th_sell_text, "TH Sell")
async def top_sell_cn(u, c): await execute_scan_command(u, scan_top_cn_sell_symbols, get_top_cn_sell_text, "CN Sell")
async def top_sell_hk(u, c): await execute_scan_command(u, scan_top_hk_sell_symbols, get_top_hk_sell_text, "HK Sell")
async def top_sell_us(u, c): await execute_scan_command(u, scan_top_us_stock_sell_symbols, get_top_us_stock_sell_text, "US Sell")
async def top_sell_all(u, c): 
    text = get_global_sell_text()
    if "กำลังสแกน" in text: await u.message.reply_text("⏳ ข้อมูล Global Sell กำลังอัปเดต...", parse_mode="Markdown")
    else: await u.message.reply_text(text, parse_mode="Markdown")

async def top_on(u, c): add_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔔 เปิดแจ้งเตือน 09:00")
async def top_off(u, c): remove_top_notify_user(u.effective_chat.id); await u.message.reply_text("🔕 ปิดแจ้งเตือน")

async def scan_market_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⚙️ Job: Heavy Scan Started")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_heavy_scan_all_markets)
    logger.info("✅ Job: Heavy Scan Completed")

async def send_daily_top(context: ContextTypes.DEFAULT_TYPE):
    logger.info("⏰ Job: Sending Daily Notify")
    users = load_top_notify_users()
    if not users: return
    
    parts = ["🌅 *DAILY MARKET*"]
    buy = get_global_top_text()
    if "กำลังสแกน" not in buy: parts.append(buy)
    
    msg = "\n\n".join(parts)
    for uid in users:
        try: await context.bot.send_message(uid, msg, parse_mode="Markdown")
        except: pass

# ======================
# MAIN
# ======================
def main():
    # ใช้ Try-Except ครอบเซิร์ฟเวอร์ ถ้าเปิดไม่ได้ก็ไม่ต้องตาย
    threading.Thread(target=run_web_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("alert", alert))
    
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
    app.job_queue.run_repeating(auto_check_alerts, interval=120, first=10)
    app.job_queue.run_daily(scan_market_job, time=time(hour=5, minute=30, tzinfo=TH_TZ))
    app.job_queue.run_daily(send_daily_top, time=time(hour=9, minute=0, tzinfo=TH_TZ))

    logger.info("🤖 Bot Started Ready!")
    app.run_polling()

if __name__ == "__main__":
    main()