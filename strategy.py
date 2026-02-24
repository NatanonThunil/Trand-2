from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import mplfinance as mpf 
import os
import requests 
from datetime import datetime
import time
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.lines as mlines # สำหรับวาด Legend
import numpy as np
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
# 🧠 CORE ANALYSIS (PRO TRADER EDITION 🎯)
# =====================
def calculate_indicators(df):
    """คำนวณอินดิเคเตอร์แบบ Multi-Dimensional"""
    # 1. Trend Indicators
    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()   
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean() 
    
    # 2. Momentum Indicators
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
    
    # 3. Volatility & Support/Resistance
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_mid'] + (2 * df['bb_std'])
    df['bb_lower'] = df['bb_mid'] - (2 * df['bb_std'])
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = ranges.max(axis=1).rolling(14).mean()

    # 4. Volume Analysis
    if 'volume' in df.columns:
        df['vol_sma'] = df['volume'].rolling(window=20).mean()
    else:
        df['vol_sma'] = 0 
    
    return df

def analyze_chart(df, mode="BUY"):
    if df is None or len(df) < 200: return 0, [], 0
    
    df = calculate_indicators(df)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    score = 0
    reasons = []
    
    if mode == "BUY":
        # 🛑 Rule 1: Trend Alignment (เข้มงวดขึ้น)
        # ไม่ใช่แค่อยู่เหนือ EMA200 แต่เส้นต้องเรียงตัวสวย (Perfect Uptrend)
        perfect_uptrend = (curr['ema_fast'] > curr['ema_slow']) and \
                          (curr['ema_slow'] > curr['ema_50']) and \
                          (curr['ema_50'] > curr['ema_200']) and \
                          (curr['close'] > curr['ema_fast'])
                          
        is_uptrend = (curr['close'] > curr['ema_200']) and (curr['ema_50'] > curr['ema_200'])

        if perfect_uptrend:
            score += 4
            reasons.append("🔥 Perfect Uptrend (เทรนด์ขาขึ้นแข็งแกร่ง)")
        elif is_uptrend:
            score += 2
            reasons.append("✅ Uptrend Confirmed (ยืนเหนือแนวรับหลัก)")
        else:
            score -= 10 # สวนเทรนด์ ตัดทิ้งทันที
            reasons.append("❌ Counter Trend")

        # 🛑 Rule 2: Price Action & Support/Resistance
        if curr['close'] < curr['bb_upper']:
            # ซื้อที่แนวรับ (Buy the Dip)
            if curr['bb_lower'] < curr['close'] <= curr['bb_mid'] * 1.02: 
                score += 3
                reasons.append("💎 Value Zone (เด้งแนวรับต้นรอบ)")
            # เพิ่งเริ่มเบรกจากโซนสะสม
            elif prev['close'] < curr['bb_mid'] and curr['close'] > curr['bb_mid']:
                score += 2
                reasons.append("🚀 Mid-Band Breakout (เริ่มมีแรงส่ง)")
        else:
            score -= 3
            reasons.append("⚠️ Overextended (ราคาแพงไป ระวังย่อ)")

        # 🛑 Rule 3: Momentum (MACD & RSI)
        if prev['macd'] < prev['signal_line'] and curr['macd'] > curr['signal_line']:
            score += 3
            reasons.append("🎯 MACD Golden Cross (จุดเข้าสุดคม)")
        elif curr['macd'] > curr['signal_line'] and curr['hist'] > prev['hist'] and curr['hist'] > 0:
            score += 1
            reasons.append("📈 Strong Momentum")

        # RSI ต้องมีพื้นที่วิ่ง ไม่ตึงเกินไป
        if 45 <= curr['rsi'] <= 65:
            score += 2
            reasons.append(f"⚖️ RSI Healthy ({curr['rsi']:.0f})")
        elif curr['rsi'] > 75:
            score -= 5 # ห้ามซื้อตอน RSI ตึงเปรี๊ยะ
            reasons.append("🔥 RSI Overbought (อันตราย)")

        # 🛑 Rule 4: Smart Money Footprint (Volume)
        if curr['vol_sma'] > 0:
            if curr['volume'] > (curr['vol_sma'] * 2.0) and curr['close'] > curr['open']:
                score += 3
                reasons.append("🐳 Massive Volume (รายใหญ่เข้าดันราคา)")
            elif curr['volume'] > (curr['vol_sma'] * 1.2) and curr['close'] > curr['open']:
                score += 1
                reasons.append("📊 Volume Supported")

    else: # SELL (หาจุด Short หรือหุ้นที่ทรงเสียหนัก)
        perfect_downtrend = (curr['ema_fast'] < curr['ema_slow']) and \
                            (curr['ema_slow'] < curr['ema_50']) and \
                            (curr['ema_50'] < curr['ema_200']) and \
                            (curr['close'] < curr['ema_fast'])
                            
        is_downtrend = (curr['close'] < curr['ema_200']) and (curr['ema_50'] < curr['ema_200'])

        if perfect_downtrend:
            score += 4
            reasons.append("🩸 Perfect Downtrend (ขาลงเต็มสูบ)")
        elif is_downtrend:
            score += 2
            reasons.append("🔻 Downtrend Confirmed")
        else:
            score -= 10
            reasons.append("❌ Counter Trend")

        if curr['close'] > curr['bb_lower']:
            # เด้งขึ้นมาชนต้าน (Pullback Short)
            if curr['bb_upper'] > curr['close'] >= curr['bb_mid'] * 0.98:
                score += 3
                reasons.append("🎯 Pullback Short (เด้งชนต้าน)")
        else:
            score -= 3
            reasons.append("⚠️ Oversold (ราคาลงลึกเกินไป)")

        if prev['macd'] > prev['signal_line'] and curr['macd'] < curr['signal_line']:
            score += 3
            reasons.append("📉 MACD Death Cross (สัญญาณทุบ)")
        
        if 35 <= curr['rsi'] <= 55:
            score += 2
            reasons.append(f"⚖️ RSI Valid for Short ({curr['rsi']:.0f})")
        elif curr['rsi'] < 25:
            score -= 5
            reasons.append("🔥 RSI Oversold (อันตราย)")
            
        if curr['vol_sma'] > 0 and curr['volume'] > (curr['vol_sma'] * 1.5) and curr['close'] < curr['open']:
            score += 3
            reasons.append("🚨 Panic Sell Volume (วอลลุ่มเทขายกระจุย)")

    return score, reasons, curr['close']

# =====================
# 🚀 SCANNER ENGINE
# =====================
def update_and_fill_market(region_name, scanner_region, cache_dict, mode="BUY", limit=500, callback=None):
    """
    ระบบสแกนแบบฉลาด: เช็ค Top 5 ตัวเดิมก่อน ถ้ายังสวยเก็บไว้ 
    ถ้าไม่สวยค่อยสแกนหาตัวใหม่มาเติมให้เต็ม 5 ตัว
    """
    tv = TvDatafeed()
    current_top = []
    
    # --- STEP 1: ตรวจสอบ Top 5 ตัวเดิม (ถ้ามี) ---
    old_results = cache_dict.get("results", [])
    if old_results:
        # print(f"Checking existing Top {len(old_results)} for {region_name}...")
        for s in old_results:
            try:
                df = tv.get_hist(symbol=s['symbol'], exchange=s['exchange'], interval=Interval.in_1_hour, n_bars=250)
                score, reasons, price = analyze_chart(df, mode=mode)
                
                # ถ้าคะแนนยังผ่านเกณฑ์ 8 คะแนน (Pro Setup) ให้เก็บไว้
                if score >= 8:
                    current_top.append({
                        "symbol": s['symbol'], "exchange": s['exchange'], 
                        "price": price, "score": score, "reasons": reasons, "region": region_name
                    })
                time.sleep(0.01)
            except: continue

    # ถ้าระบบเดิมยังแข็งแกร่งครบ 5 ตัว ไม่ต้องสแกนใหม่ให้เสียเวลา
    if len(current_top) >= 5:
        # เรียงตามคะแนน
        current_top = sorted(current_top, key=lambda x: x["score"], reverse=True)[:5]
        cache_dict["updated_at"] = datetime.now()
        cache_dict["results"] = current_top
        if callback: callback(1, 1) # บอกบอทว่าเสร็จ 100%
        return current_top

    # --- STEP 2: สแกนหาตัวใหม่มาเติมให้เต็ม 5 ---
    targets = get_stock_symbols_scanner(scanner_region, limit=limit)
    
    # กรองตัวที่อยู่ใน Top ปัจจุบันออกไปแล้ว จะได้ไม่สแกนซ้ำ
    existing_symbols = [x['symbol'] for x in current_top]
    targets = [t for t in targets if t[0] not in existing_symbols]
    
    total = len(targets)
    needed = 5 - len(current_top)
    
    for i, (symbol, exchange) in enumerate(targets):
        if callback: callback(i, total)
        
        # ถ้าได้ครบ 5 ตัวแล้ว หยุดสแกนทันที! (ประหยัดเวลามาก)
        if len(current_top) >= 5:
            break
            
        try:
            if exchange == "SZSE": exchange = "SZSE"
            df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=250)
            score, reasons, price = analyze_chart(df, mode=mode)
            
            if score >= 8:
                current_top.append({
                    "symbol": symbol, "exchange": exchange, 
                    "price": price, "score": score, "reasons": reasons, "region": region_name
                })
            time.sleep(0.01)
        except: continue

    # เรียงลำดับตัวท็อป 5 ตัว (เก่า+ใหม่ผสมกัน) ให้คนได้คะแนนสูงสุดขึ้นก่อน
    current_top = sorted(current_top, key=lambda x: x["score"], reverse=True)[:5]
    
    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = current_top
    if callback: callback(1, 1) # ส่ง 100% ตอนจบ
    return current_top


def _scan_crypto_stateful(cache_dict, mode="BUY", limit=100, callback=None):
    """ระบบสแกน Crypto แบบเดียวกับหุ้น (เช็คของเก่าก่อน)"""
    tv = TvDatafeed()
    current_top = []
    
    # 1. เช็คของเดิม
    old_results = cache_dict.get("results", [])
    if old_results:
        for s in old_results:
            try:
                df = tv.get_hist(symbol=s['symbol'], exchange="BINANCE", interval=Interval.in_1_hour, n_bars=250)
                score, reasons, price = analyze_chart(df, mode=mode)
                if score >= 8:
                    current_top.append({
                        "symbol": s['symbol'], "exchange": "BINANCE", 
                        "price": price, "score": score, "reasons": reasons, "region": "CRYPTO"
                    })
                time.sleep(0.01)
            except: continue

    if len(current_top) >= 5:
        current_top = sorted(current_top, key=lambda x: x["score"], reverse=True)[:5]
        cache_dict["updated_at"] = datetime.now()
        cache_dict["results"] = current_top
        if callback: callback(1, 1)
        return current_top

    # 2. หาตัวใหม่มาเติม
    SYMBOLS = get_top_usdt_symbols_by_volume(limit=limit)
    existing_symbols = [x['symbol'] for x in current_top]
    SYMBOLS = [s for s in SYMBOLS if s not in existing_symbols]
    
    total = len(SYMBOLS)
    
    for i, symbol in enumerate(SYMBOLS):
        if callback: callback(i, total)
        if len(current_top) >= 5: break # ได้ครบแล้วหยุด
            
        try:
            df = tv.get_hist(symbol=symbol, exchange="BINANCE", interval=Interval.in_1_hour, n_bars=250)
            score, reasons, price = analyze_chart(df, mode=mode)
            if score >= 8:
                current_top.append({
                    "symbol": symbol, "exchange": "BINANCE", 
                    "price": price, "score": score, "reasons": reasons, "region": "CRYPTO"
                })
            time.sleep(0.01)
        except: continue
        
    current_top = sorted(current_top, key=lambda x: x["score"], reverse=True)[:5]
    cache_dict["updated_at"] = datetime.now()
    cache_dict["results"] = current_top
    if callback: callback(1, 1)
    return current_top

# ==========================================
# Wrappers (เรียกใช้ระบบ Stateful ใหม่ทั้งหมด)
# ==========================================
def scan_top_th_symbols(limit=10000, callback=None): return update_and_fill_market("🇹🇭 TH", "thailand", TOP_CACHE_TH, "BUY", limit, callback)
def scan_top_cn_symbols(limit=10000, callback=None): return update_and_fill_market("🇨🇳 CN", "china", TOP_CACHE_CN, "BUY", limit, callback)
def scan_top_hk_symbols(limit=10000, callback=None): return update_and_fill_market("🇭🇰 HK", "hongkong", TOP_CACHE_HK, "BUY", limit, callback)
def scan_top_us_stock_symbols(limit=10000, callback=None): return update_and_fill_market("🇺🇸 US", "america", TOP_CACHE_US_STOCK, "BUY", limit, callback)
def scan_top_crypto_symbols(limit=10000, callback=None): return _scan_crypto_stateful(TOP_CACHE_CRYPTO, "BUY", limit, callback)

def scan_top_th_sell_symbols(limit=10000, callback=None): return update_and_fill_market("🇹🇭 TH", "thailand", TOP_SELL_CACHE_TH, "SELL", limit, callback)
def scan_top_cn_sell_symbols(limit=10000, callback=None): return update_and_fill_market("🇨🇳 CN", "china", TOP_SELL_CACHE_CN, "SELL", limit, callback)
def scan_top_hk_sell_symbols(limit=10000, callback=None): return update_and_fill_market("🇭🇰 HK", "hongkong", TOP_SELL_CACHE_HK, "SELL", limit, callback)
def scan_top_us_stock_sell_symbols(limit=10000, callback=None): return update_and_fill_market("🇺🇸 US", "america", TOP_SELL_CACHE_US_STOCK, "SELL", limit, callback)
def scan_top_crypto_sell_symbols(limit=10000, callback=None): return _scan_crypto_stateful(TOP_SELL_CACHE_CRYPTO, "SELL", limit, callback)

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
        text += f"🔥 *{i}. {s['symbol']}* `[{s['exchange']}]`\n💰 {price_fmt}\n💡 {' + '.join(s['reasons'])}\n\n"
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
                text += f" • `{s['symbol']}` [{s['exchange']}] ({price}) ➜ {reason}\n"
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
                text += f" • `{s['symbol']}` [{s['exchange']}] ({price}) ➜ {reason}\n"
            text += "\n"
    return text

# =====================
# 📈 BACKTEST STRATEGY (PRO TRADER & PRO CHART)
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

    df = calculate_indicators(df)

    capital = INITIAL_CAPITAL; position = 0; trades = 0; trade_pnls = []
    df["signal"] = 0; df["signal_price"] = np.nan
    
    for i in range(200, len(df) - 1):
        curr = df.iloc[i]; prev = df.iloc[i-1]
        
        is_uptrend = (curr['close'] > curr['ema_200']) and (curr['ema_50'] > curr['ema_200'])
        buy_condition = is_uptrend and (prev['macd'] < prev['signal_line']) and (curr['macd'] > curr['signal_line']) and (curr['rsi'] < 70)

        sell_condition = (prev['macd'] > prev['signal_line']) and (curr['macd'] < curr['signal_line'])

        if position == 0 and buy_condition:
            entry_price = df.iloc[i+1]["open"]
            position = capital / entry_price; capital = 0; trades += 1
            df.iloc[i, df.columns.get_loc("signal")] = 1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["low"] * 0.995
            
        elif position > 0 and sell_condition:
            exit_price = df.iloc[i+1]["open"]
            pnl = (exit_price - entry_price) / entry_price * 100
            trade_pnls.append(pnl)
            capital = position * exit_price; position = 0
            df.iloc[i, df.columns.get_loc("signal")] = -1
            df.iloc[i, df.columns.get_loc("signal_price")] = df.iloc[i]["high"] * 1.005
    
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
    # 🕯️ PLOT CANDLESTICK CHART (PRO CHART + LEGEND)
    # =========================================
    df_plot = df.iloc[-200:].copy()

    buy_signals = df_plot['signal_price'].where(df_plot['signal'] == 1, np.nan)
    sell_signals = df_plot['signal_price'].where(df_plot['signal'] == -1, np.nan)

    # 1. Base Indicators
    apds = [
        mpf.make_addplot(df_plot['ema_200'], color='purple', width=1.5, panel=0),
        mpf.make_addplot(df_plot['ema_50'], color='cyan', width=1, panel=0),
    ]

    # 2. Buy/Sell Signals (Check for NaN to prevent errors)
    if not buy_signals.isna().all():
        apds.append(mpf.make_addplot(buy_signals, type='scatter', markersize=120, marker='^', color='lime', panel=0))
    if not sell_signals.isna().all():
        apds.append(mpf.make_addplot(sell_signals, type='scatter', markersize=120, marker='v', color='red', panel=0))

    # 3. MACD Histogram (Fix color length issue by ensuring it matches the plotted data)
    # We create a specific color array for the exact length of the plotted data
    macd_colors = ['green' if val >= 0 else 'red' for val in df_plot['hist']]
    
    apds.extend([
        mpf.make_addplot(df_plot['hist'], type='bar', width=0.7, panel=1, color=macd_colors, alpha=0.6, ylabel='MACD'),
        mpf.make_addplot(df_plot['macd'], color='blue', width=1, panel=1),
        mpf.make_addplot(df_plot['signal_line'], color='orange', width=1, panel=1),
    ])

    # 4. Styling
    mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
    s  = mpf.make_mpf_style(
        marketcolors=mc, 
        gridstyle=':', 
        y_on_right=True, 
        facecolor='white',
        rc={'font.size': 12, 'axes.titlesize': 14, 'axes.labelsize': 10}
    )

    BASE_DIR = "/tmp"
    chart_dir = os.path.join(BASE_DIR, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    chart_path = os.path.join(chart_dir, f"{SYMBOL}_adv_candle.png")

    # 5. Plot Generation
    fig, axlist = mpf.plot(
        df_plot,
        type='candle',
        style=s,
        addplot=apds,
        volume=True,
        volume_panel=2,
        panel_ratios=(6, 2, 2),
        title=f"\n{SYMBOL} PRO Analysis (WinRate: {winrate:.1f}%)",
        figsize=(14, 10),
        scale_padding={'top': 1.5, 'bottom': 1.0, 'left': 0.8, 'right': 1.5},
        tight_layout=True,
        returnfig=True 
    )

    # 6. Legends Configuration
    ema200_line = mlines.Line2D([], [], color='purple', linewidth=1.5, label='EMA 200 (Major Trend)')
    ema50_line = mlines.Line2D([], [], color='cyan', linewidth=1, label='EMA 50 (Mid Trend)')
    buy_marker = mlines.Line2D([], [], color='none', marker='^', markerfacecolor='lime', markeredgecolor='lime', markersize=10, label='BUY Signal')
    sell_marker = mlines.Line2D([], [], color='none', marker='v', markerfacecolor='red', markeredgecolor='red', markersize=10, label='SELL Signal')
    
    # Add legend to the main price chart
    axlist[0].legend(handles=[ema200_line, ema50_line, buy_marker, sell_marker], loc='upper left', fontsize=10, framealpha=0.9)

    # Add legend to the MACD chart
    macd_line = mlines.Line2D([], [], color='blue', linewidth=1, label='MACD Line')
    sig_line = mlines.Line2D([], [], color='orange', linewidth=1, label='Signal Line')
    try:
        # axlist[2] is usually the MACD panel if volume is panel 2
        axlist[2].legend(handles=[macd_line, sig_line], loc='upper left', fontsize=10, framealpha=0.9)
    except: 
        pass 

    fig.savefig(chart_path)
    plt.close(fig) 
    
    # =========================================
    # STATUS & RETURN
    # =========================================
    last = df.iloc[-1]
    trend_st = "BULLISH 🟢" if (last['close'] > last['ema_200'] and last['ema_50'] > last['ema_200']) else "BEARISH 🔴"
    
    action = "WAIT ⏸"; entry = tp = sl = "-"
    if (last['close'] > last['ema_200'] and last['ema_50'] > last['ema_200']) and last['macd'] > last['signal_line']:
        action = "BUY ZONE 🟢 (Pro Setup)"
        entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] - (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] + (last['atr']*3):,.2f}"
    elif (last['close'] < last['ema_200'] and last['ema_50'] < last['ema_200']) and last['macd'] < last['signal_line']:
        action = "SELL ZONE 🔴 (Pro Setup)"
        entry = f"{last['close']:,.2f}"
        sl = f"SL: {last['close'] + (last['atr']*2):,.2f}"
        tp = f"TP: {last['close'] - (last['atr']*3):,.2f}"

    return {
        "text": f"""
📊 *PRO MARKET SIGNAL*
📌 Symbol : {SYMBOL}
🏢 Market : {EXCHANGE}
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