import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", 8665648263))

BACKUP_CHANNEL_ID = int(os.getenv("BACKUP_CHANNEL_ID", -1003742321028))
VIP_CHANNEL_ID = int(os.getenv("VIP_CHANNEL_ID", -1003496265510))
FREE_CHANNEL_ID = int(os.getenv("FREE_CHANNEL_ID", -1003049856005))
FILE_STORAGE_CHANNEL = int(os.getenv("FILE_STORAGE_CHANNEL", -1003754298997))

AUTO_DELETE_SECONDS = int(os.getenv("AUTO_DELETE_SECONDS", 2400))  # 40 minutes
