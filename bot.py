import logging
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from keep_alive import keep_alive

# ================= CONFIG =================
load_dotenv()

BOT_TOKEN     = os.getenv("BOT_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
ADMIN_CHAT_ID = list(map(int, filter(None, os.getenv("ADMIN_CHAT_ID", "").split(","))))

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Variables d'environnement manquantes")

# ================= INIT =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= UTILS =================
def is_admin(uid): return uid in ADMIN_CHAT_ID

def fmt(a): return f"{int(a):,} FCFA".replace(",", " ")

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Dépôts", callback_data="deps")],
        [InlineKeyboardButton("💳 Retraits", callback_data="wits")],
    ])

# ================= COMMANDES =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Accès refusé")
    await update.message.reply_text("🚀 Bot MindCash actif", reply_markup=main_keyboard())

# ================= CALLBACK =================
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not is_admin(q.from_user.id):
        return await q.edit_message_text("⛔ Accès refusé")

    if q.data == "deps":
        data = sb.table("deposits").select("*").eq("status","pending").execute().data
        if not data:
            return await q.edit_message_text("✅ Aucun dépôt")

        txt = "📥 Dépôts en attente\n\n"
        buttons = []

        for d in data:
            txt += f"💰 {fmt(d['amount'])}\n"
            buttons.append([
                InlineKeyboardButton("✅", callback_data=f"ok_{d['id']}"),
                InlineKeyboardButton("❌", callback_data=f"no_{d['id']}")
            ])

        await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(buttons))

    elif q.data.startswith("ok_"):
        did = q.data.split("_")[1]
        d = sb.table("deposits").select("*").eq("id",did).single().execute().data

        sb.table("deposits").update({"status":"success"}).eq("id",did).execute()
        sb.rpc("increment_balance", {"uid": d["user_id"], "amount": d["amount"]}).execute()

        await q.edit_message_text("✅ Dépôt validé")

    elif q.data.startswith("no_"):
        did = q.data.split("_")[1]
        sb.table("deposits").update({"status":"failed"}).eq("id",did).execute()
        await q.edit_message_text("❌ Dépôt rejeté")

# ================= MAIN =================
def main():
    # Flask keep alive
    threading.Thread(target=keep_alive, daemon=True).start()

    # Bot
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))

    async def set_cmd(app):
        await app.bot.set_my_commands([
            BotCommand("start", "Démarrer"),
        ])

    app.post_init = set_cmd

    logger.info("🚀 Bot lancé")

    app.run_polling()

# ================= RUN =================
if __name__ == "__main__":
    main()
