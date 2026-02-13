from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests 
from datetime import datetime
import time
import matplotlib
matplotlib.use('Agg')

# =====================
# 💾 CACHE STORAGE (เพิ่ม Global Cache)
# =====================
# Cache สำหรับการสแกนปกติ (กดรายครั้ง /top_th, /top_cn)
TOP_CACHE = { "exchange": "BINANCE", "updated_at": None, "results": [] }
TOP_CACHE_TH = { "region": "TH", "updated_at": None, "results": [] }
TOP_CACHE_CN = { "region": "CN", "updated_at": None, "results": [] }
TOP_CACHE_HK = { "region": "HK", "updated_at": None, "results": [] }
TOP_CACHE_US_STOCK = { "region": "US", "updated_at": None, "results": [] }

# Cache ใหญ่สำหรับ Global Scan (10,000 ตัว) - เอาไว้อ่านอย่างเดียวตอนกด /top_all
GLOBAL_CACHE_BUY = { "updated_at": None, "results": [] } 
GLOBAL_CACHE_SELL = { "updated_at": None, "results": [] }

# Sell Caches (รายประเทศ)
TOP_SELL_CACHE_USDT = { "exchange": "BINANCE", "updated_at": None, "results": [] }
TOP_SELL_CACHE_TH = { "region": "TH", "updated_at": None, "results": [] }
TOP_SELL_CACHE_CN = { "region": "CN", "updated_at": None, "results": [] }
TOP_SELL_CACHE_HK = { "region": "HK", "updated_at": None, "results": [] }
TOP_SELL_CACHE_US_STOCK = { "region": "US", "updated_at": None, "results": [] }


# =====================
# 🛠 UTILS: GET SYMBOLS
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
# 🧠 CORE: ANALYSIS LOGIC
# =====================
def analyze_chart(df, mode="BUY"):
    if df is None or len(df) < 50: return 0, [], 0
    close = df["close"]
    ema_fast = close.ewm(span=9).mean().iloc[-1]
    ema_slow = close.ewm(span=21).mean().iloc[-1]
    delta = close.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    rsi = 100 - (100 / (1 + rs.iloc[-1]))
    atr = pd.concat([df["high"]-df["low"], (df["high"]-close.shift()).abs(), (df["low"]-close.shift()).abs()], axis=1).max(axis=1).rolling(14).mean().iloc[-1]
    score = 0; reasons = []
    
    if mode == "BUY":
        if ema_fast > ema_slow: score += 2; reasons.append("EMA Uptrend")
        if rsi > 55: score += 1; reasons.append(f"RSI Strong ({rsi:.0f})")
        if 0.01 < (atr/close.iloc[-1]) < 0.15: score += 1; reasons.append("Vol (ATR)")
    else:
        if ema_fast < ema_slow: score += 2; reasons.append("EMA Downtrend")
        if rsi < 45: score += 1; reasons.append(f"RSI Weak ({rsi:.0f})")
        if close.iloc[-1] < ema_fast: score += 1; reasons.append("Price < EMA")
    return score, reasons, close.iloc[-1]

# =====================
# 🚀 SCANNER ENGINE
# =====================
def scan_generic_market(region_name, scanner_region, cache_dict, mode="BUY", limit=500):
    targets = get_stock_symbols_scanner(scanner_region, limit=limit)
    tv = TvDatafeed()
    results = []
    print(f"Scanning {region_name} {mode} ({len(targets)})...")
    
    for i, (symbol, exchange) in enumerate(targets):
        try:
            if exchange == "SZSE": exchange = "SZSE"
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=100) # ใช้ 1H ตามที่ต้องการ
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 3:
                results.append({ "symbol": symbol, "exchange": exchange, "price": price, "score": score, "reasons": reasons, "region": region_name })
            time.sleep(0.01) # เร็วขึ้น
        except: continue

    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    print(f"✅ {region_name} Done.")
    return results # Return ผลลัพธ์ทั้งหมดออกไปเพื่อเอาไปรวมใน Global Cache

def _scan_crypto(cache_dict, mode="BUY", limit=100):
    SYMBOLS = get_top_usdt_symbols_by_volume(limit=limit)
    tv = TvDatafeed()
    results = []
    print(f"Scanning Crypto {mode} ({len(SYMBOLS)})...")
    for symbol in SYMBOLS:
        try:
            df = tv.get_hist(symbol=symbol, exchange="BINANCE", interval=Interval.in_1_hour, n_bars=100)
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 3:
                results.append({ "symbol": symbol, "exchange": "BINANCE", "price": price, "score": score, "reasons": reasons, "region": "CRYPTO" })
            time.sleep(0.01)
        except: continue
    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    return results

# WRAPPERS (SCANNER ปกติ - 500 ตัว)
def scan_top_th_symbols(limit=500): return scan_generic_market("🇹🇭 TH", "thailand", TOP_CACHE_TH, "BUY", limit)
def scan_top_cn_symbols(limit=500): return scan_generic_market("🇨🇳 CN", "china", TOP_CACHE_CN, "BUY", limit)
def scan_top_hk_symbols(limit=500): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_CACHE_HK, "BUY", limit)
def scan_top_us_stock_symbols(limit=500): return scan_generic_market("🇺🇸 US", "america", TOP_CACHE_US_STOCK, "BUY", limit)
def scan_top_crypto_symbols(limit=100): return _scan_crypto(TOP_CACHE, "BUY", limit)

def scan_top_th_sell_symbols(limit=500): return scan_generic_market("🇹🇭 TH", "thailand", TOP_SELL_CACHE_TH, "SELL", limit)
def scan_top_cn_sell_symbols(limit=500): return scan_generic_market("🇨🇳 CN", "china", TOP_SELL_CACHE_CN, "SELL", limit)
def scan_top_hk_sell_symbols(limit=500): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_SELL_CACHE_HK, "SELL", limit)
def scan_top_us_stock_sell_symbols(limit=500): return scan_generic_market("🇺🇸 US", "america", TOP_SELL_CACHE_US_STOCK, "SELL", limit)
def scan_top_crypto_sell_symbols(limit=100): return _scan_crypto(TOP_SELL_CACHE_USDT, "SELL", limit)

# =====================
# 🔨 HEAVY SCAN (GLOBAL - 10,000 Symbols)
# =====================
def run_heavy_scan_all_markets():
    """
    ฟังก์ชันนี้จะสแกน 10,000 ตัว แล้วเอาผลลัพธ์ทั้งหมดไปเก็บใน GLOBAL_CACHE
    เพื่อให้คำสั่ง /top_all เรียกใช้ได้ทันทีโดยไม่ต้องรอ
    """
    print("🚀 STARTING HEAVY SCAN (10,000 symbols per market)...")
    
    # 1. Global Buy
    all_buy_results = []
    try: all_buy_results.extend(scan_top_th_symbols(limit=10000))
    except: pass
    try: all_buy_results.extend(scan_top_cn_symbols(limit=10000))
    except: pass
    try: all_buy_results.extend(scan_top_hk_symbols(limit=10000))
    except: pass
    try: all_buy_results.extend(scan_top_us_stock_symbols(limit=10000))
    except: pass
    
    # อัปเดต Cache ใหญ่
    GLOBAL_CACHE_BUY["updated_at"] = datetime.now()
    GLOBAL_CACHE_BUY["results"] = sorted(all_buy_results, key=lambda x: x["score"], reverse=True)[:20] # เก็บ Top 20 ไว้เลย
    print(f"✅ Global Buy Updated ({len(all_buy_results)} candidates found)")

    # 2. Global Sell
    all_sell_results = []
    try: all_sell_results.extend(scan_top_th_sell_symbols(limit=10000))
    except: pass
    try: all_sell_results.extend(scan_top_cn_sell_symbols(limit=10000))
    except: pass
    try: all_sell_results.extend(scan_top_hk_sell_symbols(limit=10000))
    except: pass
    try: all_sell_results.extend(scan_top_us_stock_sell_symbols(limit=10000))
    except: pass

    # อัปเดต Cache ใหญ่
    GLOBAL_CACHE_SELL["updated_at"] = datetime.now()
    GLOBAL_CACHE_SELL["results"] = sorted(all_sell_results, key=lambda x: x["score"], reverse=True)[:20]
    print(f"✅ Global Sell Updated ({len(all_sell_results)} candidates found)")
    
    print("🏁 HEAVY SCAN COMPLETE")

# =====================
# 📝 FORMATTERS
# =====================
def format_top_text(title, cache_data, decimals=2, is_sell=False):
    if not cache_data["results"]: return f"⏳ ข้อมูล {title} ยังไม่พร้อม (รอรอบสแกนถัดไป)..."
    icon = "🔴" if is_sell else "🏆"
    text = f"{icon} *TOP 5 {title}* (1H)\n\n"
    for i, s in enumerate(cache_data["results"][:5], 1): # ตัดมาแค่ 5 ตัว
        price_fmt = f"{s['price']:,.{decimals}f}"
        if s['price']<1 and decimals==2: price_fmt = f"{s['price']:,.6f}"
        text += f"🔥 *{i}. {s['symbol']}*\n💰 ราคา: {price_fmt}\n💡 {' + '.join(s['reasons'])}\n\n"
    
    if cache_data['updated_at']:
        text += f"🕒 Last Update: {cache_data['updated_at'].strftime('%H:%M')}"
    return text

# Getters รายประเทศ
def get_top_th_text(): return format_top_text("หุ้นไทย (TH)", TOP_CACHE_TH)
def get_top_cn_text(): return format_top_text("หุ้นจีน (CN)", TOP_CACHE_CN)
def get_top_hk_text(): return format_top_text("หุ้นฮ่องกง (HK)", TOP_CACHE_HK)
def get_top_us_stock_text(): return format_top_text("หุ้นอเมริกา (US)", TOP_CACHE_US_STOCK)
def get_top_crypto_text(): return format_top_text("CRYPTO", TOP_CACHE, decimals=4)

def get_top_th_sell_text(): return format_top_text("หุ้นไทย SELL", TOP_SELL_CACHE_TH, is_sell=True)
def get_top_cn_sell_text(): return format_top_text("หุ้นจีน SELL", TOP_SELL_CACHE_CN, is_sell=True)
def get_top_hk_sell_text(): return format_top_text("หุ้นฮ่องกง SELL", TOP_SELL_CACHE_HK, is_sell=True)
def get_top_us_stock_sell_text(): return format_top_text("หุ้นอเมริกา SELL", TOP_SELL_CACHE_US_STOCK, is_sell=True)
def get_top_crypto_sell_text(): return format_top_text("CRYPTO SELL", TOP_SELL_CACHE_USDT, decimals=4, is_sell=True)

# Getters Global (ดึงจาก Cache ใหญ่ได้เลย ไม่ต้องรวมใหม่)
def get_global_top_text():
    # เช็คว่า Cache มีข้อมูลไหม
    if not GLOBAL_CACHE_BUY["results"]:
        return "⏳ ข้อมูล Global (10,000 ตัว) ยังไม่พร้อม... กรุณารอระบบสแกนอัตโนมัติรอบถัดไป"
    
    text = "🌍 *TOP 10 GLOBAL BUY* (1H Scanned from 10k)\n_(คัดเน้นๆ จากทุกตลาด)_\n\n"
    for i, s in enumerate(GLOBAL_CACHE_BUY["results"][:10], 1): # ตัด Top 10
        flag = s['region'].split(' ')[0]
        reasons_str = " + ".join(s['reasons'])
        text += f"{flag} *{i}. {s['symbol']}* ({s['region']})\n💰 {s['price']:,.2f} | {reasons_str}\n\n"
    
    text += f"🕒 Last Scan: {GLOBAL_CACHE_BUY['updated_at'].strftime('%H:%M')}"
    return text

def get_global_sell_text():
    if not GLOBAL_CACHE_SELL["results"]:
        return "⏳ ข้อมูล Global Sell (10,000 ตัว) ยังไม่พร้อม... กรุณารอระบบสแกนอัตโนมัติรอบถัดไป"
    
    text = "📉 *TOP 10 GLOBAL SELL* (1H Scanned from 10k)\n_(คัดเน้นๆ จากทุกตลาด)_\n\n"
    for i, s in enumerate(GLOBAL_CACHE_SELL["results"][:10], 1):
        flag = s['region'].split(' ')[0]
        reasons_str = " + ".join(s['reasons'])
        text += f"{flag} *{i}. {s['symbol']}* ({s['region']})\n💰 {s['price']:,.2f} | {reasons_str}\n\n"
    
    text += f"🕒 Last Scan: {GLOBAL_CACHE_SELL['updated_at'].strftime('%H:%M')}"
    return text

# ======================
# 📈 BACKTEST STRATEGY
# ======================
def run_strategy(SYMBOL, EXCHANGE):
    TIMEFRAME = Interval.in_1_hour
    BARS = 5000
    FAST_EMA = 9; SLOW_EMA = 21; RSI_LEN = 14; INITIAL_CAPITAL = 100000

    tv = TvDatafeed()
    df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=TIMEFRAME, n_bars=BARS)

    if df is None or len(df) < 100: return { "text": "❌ Error", "chart": None }

    df = df.reset_index()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)

    df["ema_fast"] = df["close"].ewm(span=FAST_EMA).mean()
    df["ema_slow"] = df["close"].ewm(span=SLOW_EMA).mean()
    df["rsi"] = 100 - (100 / (1 + df["close"].diff().clip(lower=0).rolling(14).mean() / -df["close"].diff().clip(upper=0).rolling(14).mean()))
    df["atr"] = (df["high"]-df["low"]).rolling(14).mean()

    capital = INITIAL_CAPITAL; position = 0; trades = 0; trade_pnls = []
    df["signal"] = 0; df["signal_price"] = None
    
    for i in range(1, len(df) - 1):
        ema_f, ema_s = df.iloc[i]["ema_fast"], df.iloc[i]["ema_slow"]
        prev_f, prev_s = df.iloc[i-1]["ema_fast"], df.iloc[i-1]["ema_slow"]
        if position == 0 and prev_f <= prev_s and ema_f > ema_s:
            entry_price = df.iloc[i+1]["open"]
            position = capital / entry_price; capital = 0; trades += 1
            df.iloc[i, df.columns.get_loc("signal")] = 1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["low"]
        elif position > 0 and prev_f >= prev_s and ema_f < ema_s:
            exit_price = df.iloc[i+1]["open"]
            pnl = (exit_price - entry_price) / entry_price * 100
            trade_pnls.append(pnl)
            capital = position * exit_price; position = 0
            df.iloc[i, df.columns.get_loc("signal")] = -1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["high"]
    
    final_value = capital + position * df.iloc[-1]["close"]
    profit = final_value - INITIAL_CAPITAL
    roi = (profit / INITIAL_CAPITAL) * 100

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    winrate = (len(wins) / len(trade_pnls) * 100) if trade_pnls else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    rrr = avg_win / avg_loss if avg_loss != 0 else 0

    df_plot = df.iloc[-300:]
    plt.figure(figsize=(12, 6))
    plt.plot(df_plot.index, df_plot["close"], label="Price", color="black", alpha=0.7)
    plt.plot(df_plot.index, df_plot["ema_fast"], label="EMA9", color="blue")
    plt.plot(df_plot.index, df_plot["ema_slow"], label="EMA21", color="orange")
    plt.scatter(df_plot[df_plot["signal"]==1].index, df_plot[df_plot["signal"]==1]["signal_price"], marker="^", color="green", s=100)
    plt.scatter(df_plot[df_plot["signal"]==-1].index, df_plot[df_plot["signal"]==-1]["signal_price"], marker="v", color="red", s=100)
    plt.title(f"{SYMBOL} Strategy Result (ROI: {roi:.2f}%)")
    plt.legend(); plt.grid(True, alpha=0.3)
    
    os.makedirs("charts", exist_ok=True)
    chart_path = f"charts/{SYMBOL}_backtest.png"
    plt.savefig(chart_path)
    plt.close('all')

    last = df.iloc[-1]; prev = df.iloc[-2]
    trend = "BULLISH 📈" if last["ema_fast"] > last["ema_slow"] else "BEARISH 📉"
    action = "WAIT ⏸"; entry = tp = sl = "-"

    is_gold = (prev["ema_fast"] <= prev["ema_slow"]) and (last["ema_fast"] > last["ema_slow"])
    is_up = (last["ema_fast"] > last["ema_slow"])
    if (is_gold or is_up) and (45 < last["rsi"] < 70):
        action = "BUY ✅"; entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] - (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] + (last['atr']*4):,.2f}"

    is_dead = (prev["ema_fast"] >= prev["ema_slow"]) and (last["ema_fast"] < last["ema_slow"])
    is_down = (last["ema_fast"] < last["ema_slow"])
    if (is_dead or is_down) and (30 < last["rsi"] < 55):
        action = "SELL 🔴"; entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] + (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] - (last['atr']*4):,.2f}"

    return {
        "text": f"""
📊 *MARKET SIGNAL*
📌 Symbol : {SYMBOL}
💰 Price  : {last['close']:,.2f}

📈 Trend  : {trend}
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