import os
import logging
import threading
from flask import Flask
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()

# از متغیر محیطی بخون، اگه نبود از مقدار پیش‌فرض
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "71031452"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN تنظیم نشده! توی Koyeb باید Env Variable بذاری")

logging.basicConfig(level=logging.INFO)

# --- وب سرور کوچک برای اینکه هاست رایگان بفهمه ربات آنلاینه ---
flask_app = Flask(__name__)

@flask_app.route("/")
def health():
    return "Bot is running! ✅", 200

@flask_app.route("/health")
def health_check():
    return "OK", 200

def run_flask():
    port = int(os.getenv("PORT", 8000))
    flask_app.run(host="0.0.0.0", port=port)

# --- منطق ربات ---

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # اگه ادمین خودش پیام داد، فوروارد نکن
    if update.effective_user.id == ADMIN_ID:
        return
        
    user = update.effective_user
    user_id = user.id
    name = user.full_name
    username = user.username if user.username else "ندارد"
    text = update.message.text if update.message.text else " (پیام بدون متن - عکس، فایل و ...)"

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
        await update.message.reply_text("❌ خطا در ارسال پیام.")

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_ID:
        return

    try:
        # فرمت: /reply 123456 سلام چطوری؟
        args = update.message.text.split(" ", 2)
        user_id = int(args[1])
        text = args[2]

        await context.bot.send_message(chat_id=user_id, text=text)
        await update.message.reply_text("✅ پیام ارسال شد")
    except Exception as e:
        logging.error(f"Reply error: {e}")
        await update.message.reply_text("❌ فرمت درست:\n/reply USER_ID متن پیام\nمثال:\n/reply 123456 سلام")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "سلام ادمین! 👋\n"
            "هر کسی به ربات پیام بده، برات فوروارد میشه.\n"
            "برای جواب دادن:\n/reply USER_ID متن"
        )
    else:
        await forward_to_admin(update, context)

if __name__ == "__main__":
    # 1. وب سرور رو در یک ترد جدا اجرا کن
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask health server started on port {os.getenv('PORT', 8000)}")

    # 2. ربات تلگرام رو اجرا کن
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, forward_to_admin))

    print("🤖 Bot is starting... (polling)")
    app.run_polling()
