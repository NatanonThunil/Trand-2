import json
import os

FILE = "users.json"

def load_users():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(FILE, "w") as f:
        json.dump(users, f, indent=2)

def is_new_user(chat_id):
    users = load_users()
    return chat_id not in users

def mark_user_seen(chat_id):
    users = load_users()
    if chat_id not in users:
        users.append(chat_id)
        save_users(users)
