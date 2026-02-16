import json
import os

# ✅ ต้องมี /tmp/data/ นำหน้า
FILE = "/app/data/alerts.json"

# --- เพิ่มบรรทัดนี้ ---
print(f"🟢 ALERT STORE LOADED: Using file path -> {FILE}")

def load_alerts():
    if not os.path.exists(FILE): return []
    try:
        with open(FILE, "r") as f: return json.load(f)
    except: return []

def save_alerts(alerts):
    # ✅ ต้องมีบรรทัดนี้: สร้างโฟลเดอร์ก่อนเขียน
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w") as f: json.dump(alerts, f, indent=2)

def remove_alert(alerts, item):
    return [a for a in alerts if a != item]

def format_alert_message(alert, current_price):
    symbol = alert.get('symbol', 'UNKNOWN')
    exchange = alert.get('exchange', 'UNKNOWN')
    direction = alert.get('direction', 'above')
    target_price = alert.get('price', 0)

    # คำนวณส่วนต่างเป็น % (Optional: เพื่อความเท่)
    diff = 0
    if target_price > 0:
        diff = ((current_price - target_price) / target_price) * 100

    # เลือก Icon และข้อความตามทิศทาง
    if direction == "above":
        icon = "🚀 🟢"
        action_text = "BREAKOUT (พุ่งทะลุแนวต้าน)"
        diff_text = f"+{diff:.2f}%"
    else:
        icon = "🔻 🔴"
        action_text = "BREAKDOWN (หลุดแนวรับ)"
        diff_text = f"{diff:.2f}%"

    msg = f"""
🔔 *PRICE ALERT TRIGGERED!* {icon}
━━━━━━━━━━━━━━━━━━
💎 *Asset:* `{symbol}`
🏦 *Exch:* {exchange}

🎯 *Target:* {target_price:,.2f}
💰 *Current:* *{current_price:,.2f}* ({diff_text})

⚠️ *Condition:* {action_text}
━━━━━━━━━━━━━━━━━━
    """
    return msg.strip()