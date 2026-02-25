import json
import os

# ดึง URL สำหรับเชื่อมต่อฐานข้อมูลจากตั้งค่าของ Render
MONGO_URI = os.getenv("MONGO_URI")

FILE = "/tmp/data/notify_users.json"
db_collection = None

# ถ้ามีการตั้งค่า MongoDB ระบบจะเชื่อมต่ออัตโนมัติ
if MONGO_URI:
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI)
        db = client["TradingBotDB"] # ชื่อก้อน Database
        db_collection = db["notify_users"] # ชื่อตารางเก็บข้อมูล
    except Exception as e:
        print(f"⚠️ MongoDB Connection Error: {e}")

def load_top_notify_users():
    try:
        # 🌟 โหลดจากฐานข้อมูลออนไลน์ (ข้อมูลไม่มีวันหาย)
        if db_collection is not None:
            doc = db_collection.find_one({"_id": "users_list"})
            users = doc.get("chat_ids", []) if doc else []
            return [int(x) for x in users] # บังคับเป็น int เสมอ
        
        # 📁 โหลดจากไฟล์เครื่อง (สำรองกรณีไม่ได้ต่อเน็ต)
        else:
            if not os.path.exists(FILE): return []
            with open(FILE, "r") as f: 
                users = json.load(f)
                return [int(x) for x in users]
    except Exception as e:
        print(f"❌ Load Notify Users Error: {e}")
        return []

def save_top_notify_users(users):
    try:
        # ✅ บังคับให้เป็นตัวเลข (int) และลบข้อมูลที่ซ้ำกันออกให้หมด
        users = list(set([int(x) for x in users]))
        
        # 🌟 เซฟลงฐานข้อมูลออนไลน์
        if db_collection is not None:
            db_collection.update_one(
                {"_id": "users_list"},
                {"$set": {"chat_ids": users}},
                upsert=True
            )
            
        # 📁 เซฟลงไฟล์เครื่อง
        else:
            os.makedirs(os.path.dirname(FILE), exist_ok=True)
            with open(FILE, "w") as f: json.dump(users, f)
    except Exception as e:
        print(f"❌ Save Notify Users Error: {e}")

def add_top_notify_user(chat_id):
    users = load_top_notify_users()
    chat_id = int(chat_id) # บังคับแปลงเป็นตัวเลขก่อนเช็ค
    if chat_id not in users:
        users.append(chat_id)
        save_top_notify_users(users)

def remove_top_notify_user(chat_id):
    users = load_top_notify_users()
    chat_id = int(chat_id) # บังคับแปลงเป็นตัวเลขก่อนเช็ค
    if chat_id in users:
        users.remove(chat_id)
        save_top_notify_users(users)