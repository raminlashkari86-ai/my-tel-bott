import os
import re
import logging
import threading
import sqlite3
from datetime import datetime
from flask import Flask
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("8784120583:AAHr9h-P_lTedyQXjfjy13xP3sEMtDRld50")
ADMIN_ID = int(os.getenv("ADMIN_ID", "71031452"))
DB_PATH = os.getenv("DB_PATH", "users.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN تنظیم نشده!")

logging.basicConfig(level=logging.INFO)

# --- دیتابیس ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            message_count INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def save_user(user):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT message_count FROM users WHERE user_id = ?", (user.id,))
        existing = c.fetchone()
        if existing:
            c.execute('''
                UPDATE users SET username=?, full_name=?, last_seen=?, message_count=?
                WHERE user_id=?
            ''', (user.username, user.full_name, now, existing[0]+1, user.id))
        else:
            c.execute('''
                INSERT INTO users (user_id, username, full_name, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user.id, user.username, user.full_name, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB save error: {e}")

def get_all_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, username, full_name, first_seen, last_seen, message_count FROM users ORDER BY last_seen DESC")
        users = c.fetchall()
        conn.close()
        return users
    except Exception as e:
        logging.error(f"DB get error: {e}")
        return []

def get_stats():
    users = get_all_users()
    return len(users), users

init_db()

# --- وب سرور ---

flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    total, _ = get_stats()
    return f"Bot is running! ✅ - {total} users", 200

@flask_app.route("/health")
def health_check():
    return "OK", 200

@flask_app.route("/stats")
def web_stats():
    # یک صفحه ساده برای دیدن آمار از مرورگر (با پسورد ساده)
    total, users = get_stats()
    html = f"<h1>📊 آمار ربات - {total} کاربر</h1><table border=1 cellpadding=8><tr><th>نام</th><th>یوزرنیم</th><th>آیدی</th><th>اولین پیام</th><th>آخرین پیام</th><th>تعداد پیام</th></tr>"
    for u in users:
        username = f"@{u[1]}" if u[1] else "ندارد"
        html += f"<tr><td>{u[2]}</td><td>{username}</td><td>{u[0]}</td><td>{u[3]}</td><td>{u[4]}</td><td>{u[5]}</td></tr>"
    html += "</table>"
    return html

def run_flask():
    port = int(os.getenv("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- ربات ---

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        return
        
    user = update.effective_user
    save_user(user)  # ذخیره کاربر
    
    user_id = user.id
    name = user.full_name
    username = user.username if user.username else "ندارد"
    
    if update.message.text:
        text = update.message.text
    elif update.message.caption:
        text = f"{update.message.caption} (همراه با فایل)"
    else:
        text = "(پیام بدون متن)"

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 پیام جدید:\n"
                 f"👤 نام: {name}\n"
                 f"🔗 یوزرنیم: @{username}\n"
                 f"🆔 آیدی: {user_id}\n"
                 f"💬 متن: {text}"
        )
        await update.message.reply_text("✅ پیامت ارسال شد، به زودی جواب میدم.")
    except Exception as e:
        logging.error(f"Error forwarding: {e}")

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        return

    target_user_id = None
    reply_text = None

    if update.message.reply_to_message:
        original_text = update.message.reply_to_message.text or ""
        match = re.search(r"🆔 آیدی:\s*(\d+)", original_text)
        if match:
            target_user_id = int(match.group(1))
            reply_text = update.message.text

    if not target_user_id and update.message.text and update.message.text.startswith("/reply"):
        try:
            args = update.message.text.split(" ", 2)
            target_user_id = int(args[1])
            reply_text = args[2]
        except:
            await update.message.reply_text("❌ فرمت: /reply USER_ID متن")
            return

    if target_user_id and reply_text:
        try:
            await context.bot.send_message(chat_id=target_user_id, text=reply_text)
            await update.message.reply_text(f"✅ به {target_user_id} ارسال شد")
        except Exception as e:
            await update.message.reply_text(f"❌ ارسال نشد: {e}")
    elif update.message.text and update.message.text.startswith("/"):
        return
    elif update.message.text:
        await update.message.reply_text("برای جواب: روی پیامش Reply بزن یا /reply USER_ID متن")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total, users = get_stats()
    
    if total == 0:
        await update.message.reply_text("هنوز کاربری نداری 😅")
        return

    text = f"📊 **آمار ربات**\n\n👥 کل کاربران: {total}\n\n"
    
    # 20 تای آخر رو نشون بده که پیام طولانی نشه
    for u in users[:20]:
        user_id, username, full_name, first_seen, last_seen, count = u
        uname = f"@{username}" if username else "بدون یوزرنیم"
        text += f"👤 {full_name}\n   {uname} | `{user_id}` | {count} پیام\n\n"
    
    if total > 20:
        text += f"... و {total-20} نفر دیگر\n\n"
    
    text += "📋 دستورات:\n/users - لیست کامل\n/export - خروجی CSV\n/stats - همین آمار"

    await update.message.reply_text(text, parse_mode="Markdown")

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total, users = get_stats()
    
    if total == 0:
        await update.message.reply_text("هنوز کاربری نداری")
        return

    # اگه زیادن، به صورت فایل بفرست
    if total > 30:
        # ساخت CSV
        csv_content = "user_id,username,full_name,first_seen,last_seen,message_count\n"
        for u in users:
            csv_content += f"{u[0]},{u[1] or ''},{u[2]},{u[3]},{u[4]},{u[5]}\n"
        
        with open("users_export.csv", "w", encoding="utf-8") as f:
            f.write(csv_content)
        
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=open("users_export.csv", "rb"),
            filename="users.csv",
            caption=f"📋 لیست {total} کاربر"
        )
    else:
        text = f"👥 لیست {total} کاربر:\n\n"
        for u in users:
            user_id, username, full_name, _, _, count = u
            uname = f"@{username}" if username else "ندارد"
            text += f"`{user_id}` - {full_name} - {uname} - {count} پیام\n"
        await update.message.reply_text(text, parse_mode="Markdown")

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await users_command(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        total, _ = get_stats()
        await update.message.reply_text(
            f"سلام ادمین! 👋\n\n"
            f"✅ ربات 24 ساعته آنلاینه!\n"
            f"👥 {total} کاربر تا الان\n\n"
            f"دستورات:\n"
            f"/stats - آمار کلی\n"
            f"/users - لیست کاربران با آیدی و یوزرنیم\n"
            f"/export - خروجی CSV\n\n"
            f"برای جواب دادن به کاربر:\n"
            f"روی پیامش Reply بزن"
        )
    else:
        save_user(update.effective_user)
        await forward_to_admin(update, context)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask started on port {os.getenv('PORT', 10000)}")

    app = ApplicationBuilder().token(8784120583:AAHr9h-P_lTedyQXjfjy13xP3sEMtDRld50).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply), group=0)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_to_admin), group=1)

    print("🤖 Bot is starting...")
    app.run_polling()
