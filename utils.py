import os
import subprocess
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config
import database

async def force_sub_check(update, context):
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=config.BACKUP_CHANNEL_ID, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        else:
            await send_force_sub_message(update, context)
            return False
    except Exception as e:
        await update.message.reply_text("⚠️ Bot is not an admin in the backup channel. Please contact admin.")
        return False

async def send_force_sub_message(update, context):
    chat_id = update.effective_chat.id
    try:
        invite_link = await context.bot.create_chat_invite_link(chat_id=config.BACKUP_CHANNEL_ID, member_limit=1)
        link = invite_link.invite_link
    except:
        link = "https://t.me/..."  # fallback
    text = f"❌ You must join our backup channel first:\n{link}\n\nAfter joining, click /start again."
    await context.bot.send_message(chat_id=chat_id, text=text)

async def add_user_to_vip_channel(update, context, user_id):
    """Generate one‑time invite link and send to user"""
    try:
        invite = await context.bot.create_chat_invite_link(chat_id=config.VIP_CHANNEL_ID, member_limit=1)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ You have been granted access!\nJoin the VIP channel here (one‑time use): {invite.invite_link}"
        )
        return True
    except Exception as e:
        await context.bot.send_message(chat_id=config.OWNER_ID, text=f"Failed to add user {user_id} to VIP: {e}")
        return False

async def add_watermark_to_video(input_path, output_path, watermark_text="@tharkistuff (dm/msg)"):
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vf', f"drawtext=text='{watermark_text}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=5:x=w-text_w-10:y=h-text_h-10",
        '-codec:a', 'copy',
        '-y',
        output_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"Watermark error: {e}")
        return False
