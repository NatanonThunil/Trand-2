from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import mplfinance as mpf # ✅ ต้องมีไลบรารีนี้
import os
import requests 
from datetime import datetime
import time
import matplotlib
import numpy as np # ✅ ต้องมี numpy
matplotlib.use('Agg')

# =====================
# 💾 CACHE STORAGE
# =====================
TOP_CACHE_TH = { "region": "TH", "updated_at": None, "results": [] }
TOP_CACHE_CN = { "region": "CN", "updated_at": None, "results": [] }
TOP_CACHE_HK = { "region": "HK", "updated_at": None, "results": [] }
TOP_CACHE_US_STOCK = { "region": "US", "updated_at": None, "results": [] }
TOP_CACHE_CRYPTO = { "exchange": "BINANCE", "updated_at": None, "results": [] }

TOP_SELL_CACHE_TH = { "region": "TH", "updated_at": None, "results": [] }
TOP_SELL_CACHE_CN = { "region": "CN", "updated_at": None, "results": [] }
TOP_SELL_CACHE_HK = { "region": "HK", "updated_at": None, "results": [] }
TOP_SELL_CACHE_US_STOCK = { "region": "US", "updated_at": None, "results": [] }
TOP_SELL_CACHE_CRYPTO = { "exchange": "BINANCE", "updated_at": None, "results": [] }

GLOBAL_DATA_STORE = { "TH": [], "CN": [], "HK": [], "US": [], "CRYPTO": [] }
GLOBAL_DATA_SELL_STORE = { "TH": [], "CN": [], "HK": [], "US": [], "CRYPTO": [] }
GLOBAL_LAST_UPDATE = {"time": None}

# =====================
# 🛠 UTILS
# =====================
def get_stock_symbols_scanner(region="thailand", limit=5000):
    url = f"https://scanner.tradingview.com/{region}/scan"
    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "stock"},
            {"left": "subtype", "operation": "in_range", "right": ["common", "foreign"]}, 
            {"left": "volume", "operation": "nempty"},
            {"left": "close", "operation": "greater", "right": 0.1}
        ],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}},
        "columns": ["name", "close", "volume", "change", "exchange"],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "range": [0, limit]
    }
    if region == "thailand": payload["filter"].append({"left": "exchange", "operation": "equal", "right": "SET"})
    elif region == "hongkong": payload["filter"].append({"left": "exchange", "operation": "equal", "right": "HKEX"})
    elif region == "china": payload["filter"].append({"left": "exchange", "operation": "in_range", "right": ["SSE", "SZSE"]})
    elif region == "america": payload["filter"].append({"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE"]})
    try:
        response = requests.post(url, json=payload, timeout=20)
        data = response.json()
        return [(d["d"][0], d["d"][4]) for d in data["data"]]
    except: return []

def get_top_usdt_symbols_by_volume(limit=100):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        data = requests.get(url, timeout=10).json()
        usdt_pairs = [d for d in data if d["symbol"].endswith("USDT") and not d["symbol"].endswith(("UPUSDT", "DOWNUSDT"))]
        usdt_pairs.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
        return [d["symbol"] for d in usdt_pairs[:limit]]
    except: return []

# =====================
# 🧠 CORE ANALYSIS
# =====================
def calculate_indicators(df):
    """คำนวณอินดิเคเตอร์ทั้งหมดในทีเดียว"""
    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean() # Trend Filter
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp12 - exp26
    df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['hist'] = df['macd'] - df['signal_line']
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.rolling(14).mean()
    
    return df

def analyze_chart(df, mode="BUY"):
    if df is None or len(df) < 200: return 0, [], 0
    
    df = calculate_indicators(df)
    last = df.iloc[-1]
    
    score = 0; reasons = []
    
    is_uptrend = last['close'] > last['ema_200']
    is_downtrend = last['close'] < last['ema_200']
    macd_bullish = last['macd'] > last['signal_line']
    macd_bearish = last['macd'] < last['signal_line']
    
    if mode == "BUY":
        if is_uptrend: score += 2; reasons.append("Above EMA200 (Major Uptrend)")
        else: score -= 5 
        if macd_bullish: score += 2; reasons.append("MACD Bullish")
        if 50 < last['rsi'] < 70: score += 1; reasons.append(f"RSI Healthy ({last['rsi']:.0f})")
        
    else: # SELL
        if is_downtrend: score += 2; reasons.append("Below EMA200 (Major Downtrend)")
        else: score -= 5 
        if macd_bearish: score += 2; reasons.append("MACD Bearish")
        if 30 < last['rsi'] < 50: score += 1; reasons.append(f"RSI Weak ({last['rsi']:.0f})")

    return score, reasons, last['close']

# =====================
# 🚀 SCANNER ENGINE
# =====================
def scan_generic_market(region_name, scanner_region, cache_dict, mode="BUY", limit=500, callback=None):
    targets = get_stock_symbols_scanner(scanner_region, limit=limit)
    tv = TvDatafeed()
    results = []
    total = len(targets)
    
    for i, (symbol, exchange) in enumerate(targets):
        if callback: callback(i, total)
        try:
            if exchange == "SZSE": exchange = "SZSE"
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=250)
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 4: 
                results.append({ "symbol": symbol, "exchange": exchange, "price": price, "score": score, "reasons": reasons, "region": region_name })
            time.sleep(0.01)
        except: continue

    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    return results

def _scan_crypto(cache_dict, mode="BUY", limit=100, callback=None):
    SYMBOLS = get_top_usdt_symbols_by_volume(limit=limit)
    tv = TvDatafeed()
    results = []
    total = len(SYMBOLS)
    
    for i, symbol in enumerate(SYMBOLS):
        if callback: callback(i, total)
        try:
            df = tv.get_hist(symbol=symbol, exchange="BINANCE", interval=Interval.in_1_hour, n_bars=250)
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 4:
                results.append({ "symbol": symbol, "exchange": "BINANCE", "price": price, "score": score, "reasons": reasons, "region": "CRYPTO" })
            time.sleep(0.01)
        except: continue
    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    return results

# Wrappers
def scan_top_th_symbols(limit=500, callback=None): return scan_generic_market("🇹🇭 TH", "thailand", TOP_CACHE_TH, "BUY", limit, callback)
def scan_top_cn_symbols(limit=500, callback=None): return scan_generic_market("🇨🇳 CN", "china", TOP_CACHE_CN, "BUY", limit, callback)
def scan_top_hk_symbols(limit=500, callback=None): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_CACHE_HK, "BUY", limit, callback)
def scan_top_us_stock_symbols(limit=500, callback=None): return scan_generic_market("🇺🇸 US", "america", TOP_CACHE_US_STOCK, "BUY", limit, callback)
def scan_top_crypto_symbols(limit=100, callback=None): return _scan_crypto(TOP_CACHE_CRYPTO, "BUY", limit, callback)

def scan_top_th_sell_symbols(limit=500, callback=None): return scan_generic_market("🇹🇭 TH", "thailand", TOP_SELL_CACHE_TH, "SELL", limit, callback)
def scan_top_cn_sell_symbols(limit=500, callback=None): return scan_generic_market("🇨🇳 CN", "china", TOP_SELL_CACHE_CN, "SELL", limit, callback)
def scan_top_hk_sell_symbols(limit=500, callback=None): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_SELL_CACHE_HK, "SELL", limit, callback)
def scan_top_us_stock_sell_symbols(limit=500, callback=None): return scan_generic_market("🇺🇸 US", "america", TOP_SELL_CACHE_US_STOCK, "SELL", limit, callback)
def scan_top_crypto_sell_symbols(limit=100, callback=None): return _scan_crypto(TOP_SELL_CACHE_CRYPTO, "SELL", limit, callback)

# =====================
# 🔨 HEAVY SCAN
# =====================
def run_scan_asia_market():
    GLOBAL_DATA_STORE["CN"] = scan_top_cn_symbols(limit=10000)
    GLOBAL_DATA_STORE["HK"] = scan_top_hk_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["CN"] = scan_top_cn_sell_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["HK"] = scan_top_hk_sell_symbols(limit=10000)
    GLOBAL_LAST_UPDATE["time"] = datetime.now()

def run_scan_th_market():
    GLOBAL_DATA_STORE["TH"] = scan_top_th_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["TH"] = scan_top_th_sell_symbols(limit=10000)
    GLOBAL_LAST_UPDATE["time"] = datetime.now()

def run_scan_us_market():
    GLOBAL_DATA_STORE["US"] = scan_top_us_stock_symbols(limit=10000)
    GLOBAL_DATA_STORE["CRYPTO"] = scan_top_crypto_symbols(limit=500)
    GLOBAL_DATA_SELL_STORE["US"] = scan_top_us_stock_sell_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["CRYPTO"] = scan_top_crypto_sell_symbols(limit=500)
    GLOBAL_LAST_UPDATE["time"] = datetime.now()

# =====================
# 📝 FORMATTERS
# =====================
def format_top_text(title, cache_data, decimals=2, is_sell=False):
    if not cache_data["results"]: return f"⏳ ข้อมูล {title} ยังไม่พร้อม..."
    icon = "🔴" if is_sell else "🏆"
    text = f"{icon} *TOP 5 {title}* (1H)\n\n"
    for i, s in enumerate(cache_data["results"][:5], 1):
        price_fmt = f"{s['price']:,.{decimals}f}"
        text += f"🔥 *{i}. {s['symbol']}*\n💰 {price_fmt}\n💡 {' + '.join(s['reasons'])}\n\n"
    if cache_data['updated_at']: text += f"🕒 Updated: {cache_data['updated_at'].strftime('%H:%M')}"
    return text

def get_top_th_text(): return format_top_text("หุ้นไทย (TH)", TOP_CACHE_TH)
def get_top_cn_text(): return format_top_text("หุ้นจีน (CN)", TOP_CACHE_CN)
def get_top_hk_text(): return format_top_text("หุ้นฮ่องกง (HK)", TOP_CACHE_HK)
def get_top_us_stock_text(): return format_top_text("หุ้นอเมริกา (US)", TOP_CACHE_US_STOCK)
def get_top_crypto_text(): return format_top_text("CRYPTO", TOP_CACHE_CRYPTO, decimals=4)

def get_top_th_sell_text(): return format_top_text("หุ้นไทย SELL", TOP_SELL_CACHE_TH, is_sell=True)
def get_top_cn_sell_text(): return format_top_text("หุ้นจีน SELL", TOP_SELL_CACHE_CN, is_sell=True)
def get_top_hk_sell_text(): return format_top_text("หุ้นฮ่องกง SELL", TOP_SELL_CACHE_HK, is_sell=True)
def get_top_us_stock_sell_text(): return format_top_text("หุ้นอเมริกา SELL", TOP_SELL_CACHE_US_STOCK, is_sell=True)
def get_top_crypto_sell_text(): return format_top_text("CRYPTO SELL", TOP_SELL_CACHE_CRYPTO, decimals=4, is_sell=True)

def get_global_top_text():
    if not any(GLOBAL_DATA_STORE.values()): 
        return "⏳ ข้อมูล Global ยังไม่พร้อม (รอรอบสแกน)..."
    text = "🌍 *GLOBAL MARKET OPPORTUNITIES (Buy)* 🚀\n_(คัด Top 3 เน้นๆ จากทุกตลาด)_\n\n"
    markets = [("CRYPTO", "💎 Crypto"), ("US", "🇺🇸 US Market"), ("TH", "🇹🇭 Thai Market"), ("HK", "🇭🇰 HK Market"), ("CN", "🇨🇳 China Market")]
    for key, title in markets:
        data = GLOBAL_DATA_STORE.get(key, [])
        if not data: continue
        top_picks = sorted(data, key=lambda x: x["score"], reverse=True)[:3]
        if top_picks:
            text += f"*{title}*\n"
            for s in top_picks:
                price = f"{s['price']:,.2f}"
                reason = s['reasons'][0] if s['reasons'] else "Strong Trend"
                text += f" • `{s['symbol']}` ({price}) ➜ {reason}\n"
            text += "\n"
    if GLOBAL_LAST_UPDATE["time"]: text += f"🕒 Data Updated: {GLOBAL_LAST_UPDATE['time'].strftime('%H:%M')}"
    return text

def get_global_sell_text():
    if not any(GLOBAL_DATA_SELL_STORE.values()): 
        return "⏳ ข้อมูล Global Sell ยังไม่พร้อม..."
    text = "📉 *GLOBAL MARKET WARNINGS (Sell)* 🔻\n_(ระวัง! หุ้นเหล่านี้กำลังเป็นขาลงหนัก)_\n\n"
    markets = [("CRYPTO", "💎 Crypto"), ("US", "🇺🇸 US Market"), ("TH", "🇹🇭 Thai Market"), ("HK", "🇭🇰 HK Market"), ("CN", "🇨🇳 China Market")]
    for key, title in markets:
        data = GLOBAL_DATA_SELL_STORE.get(key, [])
        if not data: continue
        top_picks = sorted(data, key=lambda x: x["score"], reverse=True)[:3]
        if top_picks:
            text += f"*{title}*\n"
            for s in top_picks:
                price = f"{s['price']:,.2f}"
                reason = s['reasons'][0] if s['reasons'] else "Downtrend"
                text += f" • `{s['symbol']}` ({price}) ➜ {reason}\n"
            text += "\n"
    return text

# =====================
# 📈 BACKTEST STRATEGY (High Accuracy + Pro Chart)
# =====================
def run_strategy(SYMBOL, EXCHANGE):
    TIMEFRAME = Interval.in_1_hour
    BARS = 3000
    INITIAL_CAPITAL = 100000

    tv = TvDatafeed()
    df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=TIMEFRAME, n_bars=BARS)

    if df is None or len(df) < 200: return { "text": "❌ Error: No Data or Symbol Invalid", "chart": None }

    df = df.reset_index()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)

    # ✅ ใช้การคำนวณแบบแม่นยำ (Trend + MACD + ATR)
    df = calculate_indicators(df)

    capital = INITIAL_CAPITAL; position = 0; trades = 0; trade_pnls = []
    df["signal"] = 0; df["signal_price"] = np.nan # ใช้ np.nan เพื่อความชัวร์ในการพลอต
    
    for i in range(200, len(df) - 1): # เริ่มที่ 200 เพื่อรอ EMA 200
        curr = df.iloc[i]; prev = df.iloc[i-1]
        
        # 🟢 BUY CONDITION: ราคา > EMA200 และ MACD ตัดขึ้น
        buy_condition = (curr['close'] > curr['ema_200']) and \
                        (prev['macd'] < prev['signal_line']) and (curr['macd'] > curr['signal_line']) and \
                        (curr['rsi'] < 70)

        # 🔴 SELL CONDITION: ราคา < EMA200 และ MACD ตัดลง
        sell_condition = (curr['close'] < curr['ema_200']) and \
                         (prev['macd'] > prev['signal_line']) and (curr['macd'] < curr['signal_line']) and \
                         (curr['rsi'] > 30)

        # EXECUTE
        if position == 0 and buy_condition:
            entry_price = df.iloc[i+1]["open"]
            position = capital / entry_price; capital = 0; trades += 1
            df.iloc[i, df.columns.get_loc("signal")] = 1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["low"] * 0.995 # วางจุดต่ำกว่าแท่งเทียน
            
        elif position > 0 and (curr['macd'] < curr['signal_line']): # EXIT (Profit/Loss)
            exit_price = df.iloc[i+1]["open"]
            pnl = (exit_price - entry_price) / entry_price * 100
            trade_pnls.append(pnl)
            capital = position * exit_price; position = 0
            df.iloc[i, df.columns.get_loc("signal")] = -1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["high"] * 1.005 # วางจุดสูงกว่าแท่งเทียน
    
    final_value = capital + position * df.iloc[-1]["close"]
    profit = final_value - INITIAL_CAPITAL
    roi = (profit / INITIAL_CAPITAL) * 100
    
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    winrate = (len(wins) / len(trade_pnls) * 100) if trade_pnls else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    rrr = avg_win / avg_loss if avg_loss != 0 else 0
    
    # =========================================
    # 🕯️ PLOT CANDLESTICK CHART (ส่วนที่แก้ไข)
    # =========================================
    # ตัดข้อมูลมาแสดงผลแค่ 250 แท่งล่าสุด เพื่อความคมชัด
    df_plot = df.iloc[-250:].copy()

    buy_signals = df_plot['signal_price'].where(df_plot['signal'] == 1, np.nan)
    sell_signals = df_plot['signal_price'].where(df_plot['signal'] == -1, np.nan)

    apds = [
        # Panel 0: Main (Price + EMA)
        mpf.make_addplot(df_plot['ema_200'], color='purple', width=1.5, panel=0),
        mpf.make_addplot(df_plot['ema_fast'], color='cyan', width=0.8, panel=0),
        mpf.make_addplot(buy_signals, type='scatter', markersize=100, marker='^', color='lime', panel=0),
        mpf.make_addplot(sell_signals, type='scatter', markersize=100, marker='v', color='red', panel=0),
        
        # Panel 1: MACD
        mpf.make_addplot(df_plot['hist'], type='bar', width=0.7, panel=1, color=['green' if x >= 0 else 'red' for x in df_plot['hist']], alpha=0.6, ylabel='MACD'),
        mpf.make_addplot(df_plot['macd'], color='blue', width=1, panel=1),
        mpf.make_addplot(df_plot['signal_line'], color='orange', width=1, panel=1),
    ]

    # Create Custom Style (Large Font + Clean Look)
    mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
    s  = mpf.make_mpf_style(
        marketcolors=mc, 
        gridstyle=':', 
        y_on_right=True, 
        facecolor='white',
        rc={
            'font.size': 12,
            'axes.titlesize': 14,
            'axes.labelsize': 10
        }
    )

    BASE_DIR = "/tmp"
    chart_dir = os.path.join(BASE_DIR, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    chart_path = os.path.join(chart_dir, f"{SYMBOL}_adv_candle.png")

    # ✅ Layout Fix: Add Padding & Resize
    mpf.plot(
        df_plot,
        type='candle',
        style=s,
        addplot=apds,
        volume=True,
        volume_panel=2,         # ย้าย Volume ไปล่างสุด (Index 2)
        panel_ratios=(6, 2, 2), # สัดส่วนความสูง
        title=f"\n{SYMBOL} Professional Chart (WinRate: {winrate:.1f}%)",
        figsize=(14, 10),       # ขยายขนาดรูป
        scale_padding={'top': 1.5, 'bottom': 1.0, 'left': 0.8, 'right': 1.5}, # ดันกราฟลงมา
        tight_layout=True,
        savefig=chart_path
    )

    last = df.iloc[-1]
    trend_st = "BULLISH 🟢" if last['close'] > last['ema_200'] else "BEARISH 🔴"
    
    action = "WAIT ⏸"; entry = tp = sl = "-"
    if last['close'] > last['ema_200'] and last['macd'] > last['signal_line']:
        action = "BUY ZONE 🟢"
        entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] - (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] + (last['atr']*3):,.2f}"
    elif last['close'] < last['ema_200'] and last['macd'] < last['signal_line']:
        action = "SELL ZONE 🔴"
        entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] + (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] - (last['atr']*3):,.2f}"

    return {
        "text": f"""
📊 *MARKET SIGNAL*
📌 Symbol : {SYMBOL}
💰 Price  : {last['close']:,.2f}

📈 Trend  : {trend_st}
📊 RSI    : {last['rsi']:.2f}
📉 ATR    : {last['atr']:.2f}

⚡ *Action* : {action}
🎯 Entry   : {entry}
{tp}
{sl}

=====================
📈 *BACKTEST RESULT*
=====================
💼 Final Portfolio : {final_value:,.2f}
💰 Profit          : {profit:,.2f}
📊 ROI             : {roi:.2f}%
=====================
👑 Winrate        : {winrate:.2f}%
📈 Avg Win        : {avg_win:.2f}%
📉 Avg Loss       : {avg_loss:.2f}%
⚖️ RRR            : {rrr:.2f}
🔁 Trades          : {trades}
""",
        "chart": chart_path
    }