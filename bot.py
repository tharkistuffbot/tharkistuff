#!/usr/bin/env python3
import logging
import random
import string
import sqlite3
import os
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import config
import database
import utils

# Enable logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

database.init_db()
database.upgrade_db_for_subscriptions()

# ---- Background Jobs ----

async def delete_expired_messages(context: ContextTypes.DEFAULT_TYPE):
    now = int(datetime.now().timestamp())
    expired = database.get_expired_files(now)
    for chat_id, msg_id in expired:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.info(f"Deleted expired message {msg_id}")
        except Exception as e:
            logger.warning(f"Could not delete {chat_id}/{msg_id}: {e}")

async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """Daily job: kick expired users and send renewal offers"""
    expired = database.get_expired_users()
    for user_id, first_name, username, end_date in expired:
        try:
            # Remove from VIP channel
            await context.bot.ban_chat_member(chat_id=config.VIP_CHANNEL_ID, user_id=user_id)
            database.remove_user_subscription(user_id)
            # Send renewal offer
            discount_link = f"https://t.me/{context.bot.username}?start=renew_{user_id}"
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"⚠️ *Your VIP subscription has expired.*\n\n"
                    f"💎 But good news! As a returning member, you get a **15% discount** on renewal!\n\n"
                    f"👉 [Click here to renew with 15% off]({discount_link})\n\n"
                    f"Questions? Contact @tharkistuff"
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")

async def check_upcoming_expirations(context: ContextTypes.DEFAULT_TYPE):
    """Daily job: send reminders 3 days and 1 day before expiry"""
    for days in [3, 1]:
        users = database.get_users_expiring_soon(days)
        for user_id, first_name, username, end_date in users:
            # Check if reminder already sent
            if days == 3:
                # Need a way to check reminder_sent_3d – we'll add a helper later
                # For simplicity, we skip if already sent; we can implement later.
                pass
            end_date_obj = datetime.fromisoformat(end_date)
            end_date_str = end_date_obj.strftime("%d %b %Y")
            if days == 3:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔔 *Reminder: Your VIP subscription ends in 3 days!*\n\n"
                        f"📅 Expiry date: {end_date_str}\n\n"
                        f"💎 Renew now to avoid interruption.\n"
                        f"Contact @tharkistuff for renewal options."
                    ),
                    parse_mode='Markdown'
                )
            else:  # 1 day
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚠️ *URGENT: Your VIP subscription ends TOMORROW!*\n\n"
                        f"📅 Last day: {end_date_str}\n\n"
                        f"💎 Don't lose access – renew today!\n"
                        f"Contact @tharkistuff for renewal options."
                    ),
                    parse_mode='Markdown'
                )
            # Mark sent (you can implement a database function for this)

# ---- Helper to send with auto-delete ----
async def send_with_auto_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode=None, reply_markup=None):
    msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
    delete_time = int((datetime.now() + timedelta(seconds=config.AUTO_DELETE_SECONDS)).timestamp())
    database.add_file(f"msg_{msg.message_id}", msg.chat_id, msg.message_id, delete_time)
    return msg

# ---- Command Handlers ----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    database.add_user(user.id, user.username, user.first_name)
    if not await utils.force_sub_check(update, context):
        return
    text = (f"👋 Welcome {user.first_name}!\n\n"
            "• Use /buy to purchase VIP access.\n"
            "• Admins: use /batch to create batch links.")
    await send_with_auto_delete(update, context, text)

async def batch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    await update.message.reply_text(
        "📦 Batch link creation:\n"
        "1. Go to the file storage channel.\n"
        "2. Forward me the messages you want to include.\n"
        "3. When done, send /done."
    )
    context.user_data['batch_files'] = []

async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.forward_from_chat and update.message.forward_from_chat.id == config.FILE_STORAGE_CHANNEL:
        if 'batch_files' not in context.user_data:
            context.user_data['batch_files'] = []
        original_msg_id = update.message.forward_from_message_id
        context.user_data['batch_files'].append(original_msg_id)
        await update.message.reply_text(f"✅ Added. Total: {len(context.user_data['batch_files'])}")

async def done_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'batch_files' not in context.user_data or not context.user_data['batch_files']:
        await update.message.reply_text("No files collected.")
        return
    batch_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    database.save_batch(batch_id, context.user_data['batch_files'])
    link = f"https://t.me/{context.bot.username}?start=batch_{batch_id}"
    await update.message.reply_text(f"✅ Batch link created:\n{link}\n\nShare this link in your free channel.")
    del context.user_data['batch_files']

async def batch_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return
    param = context.args[0]
    if param.startswith("batch_"):
        batch_id = param[6:]
        file_ids = database.get_batch(batch_id)
        if not file_ids:
            await update.message.reply_text("Invalid or expired batch link.")
            return
        if not await utils.force_sub_check(update, context):
            return
        for msg_id in file_ids:
            try:
                await context.bot.forward_message(chat_id=update.effective_chat.id,
                                                  from_chat_id=config.FILE_STORAGE_CHANNEL,
                                                  message_id=int(msg_id))
            except Exception as e:
                logger.error(f"Failed to forward message {msg_id}: {e}")
        upsell = ("⚠️ *These videos will be deleted in 40 minutes!*\n\n"
                  "💎 Want LIFETIME access with NO DELETION?\n"
                  "Click /buy to purchase VIP membership.")
        await send_with_auto_delete(update, context, upsell, parse_mode='Markdown')

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("7 Days - ₹50", callback_data="plan_7d")],
        [InlineKeyboardButton("15 Days - ₹101", callback_data="plan_15d")],
        [InlineKeyboardButton("30 Days - ₹179", callback_data="plan_30d")],
        [InlineKeyboardButton("6 Months - ₹499", callback_data="plan_6m")],
        [InlineKeyboardButton("Lifetime (with sharing) - ₹849", callback_data="plan_lifetime")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a plan:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    plan_days = {
        "plan_7d": 7,
        "plan_15d": 15,
        "plan_30d": 30,
        "plan_6m": 180,
        "plan_lifetime": 36500
    }

    plan_names = {
        "plan_7d": "7 Days",
        "plan_15d": "15 Days",
        "plan_30d": "30 Days",
        "plan_6m": "6 Months",
        "plan_lifetime": "Lifetime (with sharing)"
    }

    if data in plan_days:
        days = plan_days[data]
        plan_name = plan_names[data]

        await query.edit_message_text(f"⏳ Processing payment for {plan_name}... (PVRSellGram integration will go here)")

        # After successful payment, add user to VIP channel
        success = await utils.add_user_to_vip_channel(update, context, user_id)
        if success:
            database.set_subscription(user_id, days, data)
            await query.edit_message_text(
                f"✅ Payment successful! You have been granted {plan_name} access.\n"
                f"Check your PM for the VIP channel invite link."
            )
        else:
            await query.edit_message_text("❌ Failed to add you to VIP. Please contact admin.")

async def upload_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        await update.message.reply_text("❌ Only owner can upload videos.")
        return
    await update.message.reply_text(
        "📤 Send me the video you want to watermark.\n"
        "I'll add '@tharkistuff (dm/msg)' to it and save to storage channel."
    )
    context.user_data['expecting_video'] = True

async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('expecting_video'):
        return
    if update.effective_user.id != config.OWNER_ID:
        return

    video = update.message.video
    if not video:
        await update.message.reply_text("❌ Please send a video file.")
        return

    await update.message.reply_text("⏳ Downloading video...")
    temp_dir = "temp_videos"
    os.makedirs(temp_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    input_path = f"{temp_dir}/{file_id}_input.mp4"
    output_path = f"{temp_dir}/{file_id}_watermarked.mp4"

    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(input_path)

        await update.message.reply_text("⏳ Adding watermark...")

        success = await utils.add_watermark_to_video(input_path, output_path)

        if success:
            with open(output_path, 'rb') as f:
                sent_message = await context.bot.send_video(
                    chat_id=config.FILE_STORAGE_CHANNEL,
                    video=f,
                    caption=f"✅ Watermarked video ready"
                )
            await update.message.reply_text(f"✅ Watermark added and saved! Message ID: {sent_message.message_id}")
        else:
            await update.message.reply_text("❌ Failed to add watermark. Check FFmpeg.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        for p in [input_path, output_path]:
            try:
                if os.path.exists(p): os.remove(p)
            except:
                pass
        context.user_data['expecting_video'] = False

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    conn = sqlite3.connect(database.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_premium=1")
    premium = c.fetchone()[0]
    conn.close()
    text = f"📊 Stats:\nTotal users: {total}\nPremium users: {premium}"
    await update.message.reply_text(text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = ' '.join(context.args)
    conn = sqlite3.connect(database.DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    success = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            success += 1
        except:
            pass
    await update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users.")

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    try:
        target = int(context.args[0])
        days = int(context.args[1])
    except:
        await update.message.reply_text("Usage: /addpremium <user_id> <days>")
        return
    database.set_subscription(target, days, "admin")
    invite = await context.bot.create_chat_invite_link(chat_id=config.VIP_CHANNEL_ID, member_limit=1)
    await context.bot.send_message(chat_id=target, text=f"✅ You have been granted {days} days VIP access!\nJoin here: {invite.invite_link}")
    await update.message.reply_text(f"✅ User {target} added for {days} days.")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.OWNER_ID:
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("Usage: /removepremium <user_id>")
        return
    try:
        await context.bot.ban_chat_member(chat_id=config.VIP_CHANNEL_ID, user_id=target)
        database.remove_user_subscription(target)
        await update.message.reply_text(f"✅ User {target} removed from VIP.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ---- Main ----
def main():
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("batch", batch_command))
    application.add_handler(CommandHandler("done", done_batch))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addpremium", add_premium_command))
    application.add_handler(CommandHandler("removepremium", remove_premium_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("upload", upload_video_command))

    # Deep link handlers
    application.add_handler(CommandHandler("start", batch_access, filters=filters.COMMAND & filters.Regex(r'^/start batch_')))

    # Message handlers
    application.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, handle_forwarded))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, handle_video_upload))

    # Callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Job queue
    job_queue = application.job_queue
    job_queue.run_repeating(delete_expired_messages, interval=60, first=10)
    job_queue.run_daily(check_expired_subscriptions, time=datetime.time(hour=2, minute=0))   # 2 AM daily
    job_queue.run_daily(check_upcoming_expirations, time=datetime.time(hour=10, minute=0))  # 10 AM daily

    # Start bot
    application.run_polling()

if __name__ == "__main__":
    main()
