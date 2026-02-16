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
        if 0.01 < (atr/close.iloc[-1]) < 0.15: score += 1; reasons.append("Vol OK")
    else:
        if ema_fast < ema_slow: score += 2; reasons.append("EMA Downtrend")
        if rsi < 45: score += 1; reasons.append(f"RSI Weak ({rsi:.0f})")
        if close.iloc[-1] < ema_fast: score += 1; reasons.append("Price < EMA")
    return score, reasons, close.iloc[-1]

# =====================
# 🚀 SCANNER ENGINE (Updated with Callback)
# =====================
def scan_generic_market(region_name, scanner_region, cache_dict, mode="BUY", limit=500, callback=None):
    targets = get_stock_symbols_scanner(scanner_region, limit=limit)
    tv = TvDatafeed()
    results = []
    total = len(targets)
    print(f"Scanning {region_name} {mode} ({total})...")
    
    for i, (symbol, exchange) in enumerate(targets):
        # ✅ เรียก Callback ส่ง % กลับไปหา Bot
        if callback: callback(i, total)
        
        try:
            if exchange == "SZSE": exchange = "SZSE"
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=100)
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 3:
                results.append({ "symbol": symbol, "exchange": exchange, "price": price, "score": score, "reasons": reasons, "region": region_name })
            time.sleep(0.01) # Sleep นิดหน่อยเพื่อให้ CPU หายใจ (ช่วยให้ Non-blocking ดีขึ้น)
        except: continue

    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = sorted(results, key=lambda x: x["score"], reverse=True)[:5]
    print(f"✅ {region_name} Done.")
    return results

def _scan_crypto(cache_dict, mode="BUY", limit=100, callback=None):
    SYMBOLS = get_top_usdt_symbols_by_volume(limit=limit)
    tv = TvDatafeed()
    results = []
    total = len(SYMBOLS)
    print(f"Scanning Crypto {mode} ({total})...")
    
    for i, symbol in enumerate(SYMBOLS):
        # ✅ เรียก Callback
        if callback: callback(i, total)

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

# Wrappers (รับ callback เพิ่ม)
def scan_top_th_symbols(limit=500, callback=None): return scan_generic_market("🇹🇭 TH", "thailand", TOP_CACHE_TH, "BUY", limit, callback)
def scan_top_cn_symbols(limit=500, callback=None): return scan_generic_market("🇨🇳 CN", "china", TOP_CACHE_CN, "BUY", limit, callback)
def scan_top_hk_symbols(limit=500, callback=None): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_CACHE_HK, "BUY", limit, callback)
def scan_top_us_stock_symbols(limit=500, callback=None): return scan_generic_market("🇺🇸 US", "america", TOP_CACHE_US_STOCK, "BUY", limit, callback)
def scan_top_crypto_symbols(limit=500, callback=None): return _scan_crypto(TOP_CACHE_CRYPTO, "BUY", limit, callback)

def scan_top_th_sell_symbols(limit=500, callback=None): return scan_generic_market("🇹🇭 TH", "thailand", TOP_SELL_CACHE_TH, "SELL", limit, callback)
def scan_top_cn_sell_symbols(limit=500, callback=None): return scan_generic_market("🇨🇳 CN", "china", TOP_SELL_CACHE_CN, "SELL", limit, callback)
def scan_top_hk_sell_symbols(limit=500, callback=None): return scan_generic_market("🇭🇰 HK", "hongkong", TOP_SELL_CACHE_HK, "SELL", limit, callback)
def scan_top_us_stock_sell_symbols(limit=500, callback=None): return scan_generic_market("🇺🇸 US", "america", TOP_SELL_CACHE_US_STOCK, "SELL", limit, callback)
def scan_top_crypto_sell_symbols(limit=500, callback=None): return _scan_crypto(TOP_SELL_CACHE_CRYPTO, "SELL", limit, callback)

# =====================
# 🔨 HEAVY SCAN
# =====================
def run_scan_asia_market():
    print("🚀 [Job] Scanning ASIA Market (CN+HK) 10k...")
    GLOBAL_DATA_STORE["CN"] = scan_top_cn_symbols(limit=10000)
    GLOBAL_DATA_STORE["HK"] = scan_top_hk_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["CN"] = scan_top_cn_sell_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["HK"] = scan_top_hk_sell_symbols(limit=10000)
    GLOBAL_LAST_UPDATE["time"] = datetime.now()

def run_scan_th_market():
    print("🚀 [Job] Scanning TH Market 10k...")
    GLOBAL_DATA_STORE["TH"] = scan_top_th_symbols(limit=10000)
    GLOBAL_DATA_SELL_STORE["TH"] = scan_top_th_sell_symbols(limit=10000)
    GLOBAL_LAST_UPDATE["time"] = datetime.now()

def run_scan_us_market():
    print("🚀 [Job] Scanning US Market 10k + Crypto...")
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
    if cache_data['updated_at']: text += f"🕒 Last Update: {cache_data['updated_at'].strftime('%H:%M')}"
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
    all_results = []
    for market in GLOBAL_DATA_STORE: all_results.extend(GLOBAL_DATA_STORE[market])
    if not all_results: return "⏳ ข้อมูล Global ยังไม่พร้อม (รอรอบสแกน)..."
    sorted_res = sorted(all_results, key=lambda x: x["score"], reverse=True)[:15]
    text = "🌍 *TOP 15 GLOBAL BUY* (All Markets)\n\n"
    for i, s in enumerate(sorted_res, 1):
        flag = s['region'].split(' ')[0]
        text += f"{flag} *{i}. {s['symbol']}* ({s['region']})\n💰 {s['price']:,.2f}\n\n"
    if GLOBAL_LAST_UPDATE["time"]: text += f"🕒 Last Job: {GLOBAL_LAST_UPDATE['time'].strftime('%H:%M')}"
    return text

def get_global_sell_text():
    all_results = []
    for market in GLOBAL_DATA_SELL_STORE: all_results.extend(GLOBAL_DATA_SELL_STORE[market])
    if not all_results: return "⏳ ข้อมูล Global Sell ยังไม่พร้อม (รอรอบสแกน)..."
    sorted_res = sorted(all_results, key=lambda x: x["score"], reverse=True)[:15]
    text = "📉 *TOP 15 GLOBAL SELL* (All Markets)\n\n"
    for i, s in enumerate(sorted_res, 1):
        flag = s['region'].split(' ')[0]
        text += f"{flag} *{i}. {s['symbol']}* ({s['region']})\n💰 {s['price']:,.2f}\n\n"
    return text

# =====================
# 📈 BACKTEST STRATEGY
# =====================
def run_strategy(SYMBOL, EXCHANGE):
    TIMEFRAME = Interval.in_1_hour
    BARS = 5000
    FAST_EMA = 9; SLOW_EMA = 21; INITIAL_CAPITAL = 100000

    tv = TvDatafeed()
    df = tv.get_hist(symbol=SYMBOL, exchange=EXCHANGE, interval=TIMEFRAME, n_bars=BARS)

    if df is None or len(df) < 100: return { "text": "❌ Error: No Data or Symbol Invalid", "chart": None }

    df = df.reset_index()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)

    df["ema_fast"] = df["close"].ewm(span=FAST_EMA).mean()
    df["ema_slow"] = df["close"].ewm(span=SLOW_EMA).mean()
    
    # RSI Calculation
    delta = df["close"].diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # ATR Calculation
    df["atr"] = pd.concat([df["high"]-df["low"], (df["high"]-df["close"].shift()).abs(), (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1).rolling(14).mean()

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

    # PLOT
    df_plot = df.iloc[-300:]
    plt.figure(figsize=(12, 6))
    plt.plot(df_plot.index, df_plot["close"], label="Price", color="black", alpha=0.7)
    plt.plot(df_plot.index, df_plot["ema_fast"], label="EMA9", color="blue")
    plt.plot(df_plot.index, df_plot["ema_slow"], label="EMA21", color="orange")
    plt.scatter(df_plot[df_plot["signal"]==1].index, df_plot[df_plot["signal"]==1]["signal_price"], marker="^", color="green", s=100)
    plt.scatter(df_plot[df_plot["signal"]==-1].index, df_plot[df_plot["signal"]==-1]["signal_price"], marker="v", color="red", s=100)
    plt.title(f"{SYMBOL} Strategy Result (ROI: {roi:.2f}%)")
    plt.legend(); plt.grid(True, alpha=0.3)
    
    BASE_DIR = "/tmp"
    chart_dir = os.path.join(BASE_DIR, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    chart_path = os.path.join(chart_dir, f"{SYMBOL}_backtest.png")
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