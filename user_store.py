import json
import os

# ✅ ต้องมี /tmp/data/ นำหน้า
FILE = "/tmp/data/users.json"

def load_users():
    if not os.path.exists(FILE): return []
    try:
        with open(FILE, "r") as f: return json.load(f)
    except: return []

def save_users(users):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w") as f: json.dump(users, f)

def is_new_user(chat_id):
    return chat_id not in load_users()

def mark_user_seen(chat_id):
    users = load_users()
    if chat_id not in users:
        users.append(chat_id)
        save_users(users)