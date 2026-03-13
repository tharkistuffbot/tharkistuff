import sqlite3
from datetime import datetime, timedelta

DB_FILE = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  joined_date TEXT,
                  is_premium INTEGER DEFAULT 0,
                  subscription_end_date TEXT,
                  subscription_plan TEXT,
                  reminder_sent_3d INTEGER DEFAULT 0,
                  reminder_sent_1d INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS files
                 (file_id TEXT PRIMARY KEY,
                  chat_id INTEGER,
                  message_id INTEGER,
                  delete_time INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS batches
                 (batch_id TEXT PRIMARY KEY,
                  file_ids TEXT,
                  created_at TEXT)''')
    conn.commit()
    conn.close()

def upgrade_db_for_subscriptions():
    """Ensure all columns exist (safe to run on startup)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Add columns if missing (SQLite ignores if exists)
    try:
        c.execute("ALTER TABLE users ADD COLUMN subscription_end_date TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN subscription_plan TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN reminder_sent_3d INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN reminder_sent_1d INTEGER DEFAULT 0")
    except:
        pass
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date) VALUES (?,?,?,?)",
              (user_id, username, first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def set_subscription(user_id, days, plan_id):
    end_date = (datetime.now() + timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE users SET 
        is_premium = 1,
        subscription_end_date = ?,
        subscription_plan = ?,
        reminder_sent_3d = 0,
        reminder_sent_1d = 0
        WHERE user_id = ?
    """, (end_date, plan_id, user_id))
    conn.commit()
    conn.close()

def remove_user_subscription(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        UPDATE users SET 
        is_premium = 0,
        subscription_end_date = NULL,
        subscription_plan = NULL
        WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()

def get_expired_users():
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT user_id, first_name, username, subscription_end_date 
        FROM users 
        WHERE is_premium = 1 AND subscription_end_date < ?
    """, (now,))
    users = c.fetchall()
    conn.close()
    return users

def get_users_expiring_soon(days_before):
    future = (datetime.now() + timedelta(days=days_before)).isoformat()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT user_id, first_name, username, subscription_end_date 
        FROM users 
        WHERE is_premium = 1 AND subscription_end_date BETWEEN ? AND ?
    """, (now, future))
    users = c.fetchall()
    conn.close()
    return users

def mark_reminder_sent(user_id, days):
    col = "reminder_sent_3d" if days == 3 else "reminder_sent_1d"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(f"UPDATE users SET {col} = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_file(file_id, chat_id, message_id, delete_time):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO files (file_id, chat_id, message_id, delete_time) VALUES (?,?,?,?)",
              (file_id, chat_id, message_id, delete_time))
    conn.commit()
    conn.close()

def get_expired_files(now):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, message_id FROM files WHERE delete_time < ?", (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_file_record(file_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM files WHERE file_id=?", (file_id,))
    conn.commit()
    conn.close()

def save_batch(batch_id, file_ids):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO batches (batch_id, file_ids, created_at) VALUES (?,?,?)",
              (batch_id, ','.join(str(f) for f in file_ids), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_batch(batch_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT file_ids FROM batches WHERE batch_id=?", (batch_id,))
    row = c.fetchone()
    conn.close()
    return row[0].split(',') if row else None
