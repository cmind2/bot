import os
from threading import Thread
from flask import Flask
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# ─────────────────────────────
# KEEP ALIVE (Flask)
# ─────────────────────────────
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "✅ MindCash Bot actif"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN manquant")
if not SUPABASE_URL:
    raise Exception("❌ SUPABASE_URL manquant")
if not SUPABASE_KEY:
    raise Exception("❌ SUPABASE_SERVICE_KEY manquant")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

DEPOT_MIN = int(os.getenv("DEPOT_MIN", 5000))
RETRAIT_MIN = int(os.getenv("RETRAIT_MIN", 4450))
SHOP_MIN = int(os.getenv("SHOP_MIN", 2500))
SHOP_FEE = int(os.getenv("SHOP_FEE", 3))

# ─────────────────────────────
# HELPERS
# ─────────────────────────────
def fmt(n):
    return f"{n:,}".replace(",", " ")

def now():
    return datetime.now(timezone.utc).isoformat()

async def get_user(tg_id):
    res = sb.table("users").select("*").eq("telegram_id", tg_id).maybe_single().execute()
    return res.data

# ─────────────────────────────
# START
# ─────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)

    if not user:
        await update.message.reply_text("❌ Compte non trouvé. Inscris-toi sur le site.")
        return

    await update.message.reply_text(
        f"👤 {user['name']}\n💰 {fmt(user.get('balance', 0))} FCFA",
        reply_markup=menu(user.get("is_active"))
    )

# ─────────────────────────────
# MENU
# ─────────────────────────────
def menu(active):
    if active:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Solde", callback_data="solde")],
            [InlineKeyboardButton("💳 Retrait", callback_data="retrait")],
            [InlineKeyboardButton("🛒 Boutique", callback_data="shop")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Activer", callback_data="depot")]
        ])

# ─────────────────────────────
# SOLDE
# ─────────────────────────────
async def solde(update: Update, ctx):
    query = update.callback_query
    await query.answer()

    user = await get_user(query.from_user.id)

    await query.message.reply_text(
        f"💰 Solde principal: {fmt(user.get('balance', 0))}\n"
        f"🛒 Boutique: {fmt(user.get('shop_balance', 0))}"
    )

# ─────────────────────────────
# RETRAIT BOUTIQUE
# ─────────────────────────────
async def retrait_shop(update: Update, ctx):
    query = update.callback_query
    await query.answer()

    ctx.user_data["step"] = "shop_withdraw_num"

    await query.message.reply_text("📱 Numéro MTN MoMo :")

async def handle_message(update: Update, ctx):
    step = ctx.user_data.get("step")

    if step == "shop_withdraw_num":
        ctx.user_data["num"] = update.message.text
        ctx.user_data["step"] = "shop_withdraw_amount"
        await update.message.reply_text(f"💰 Montant min {SHOP_MIN}")
        return

    if step == "shop_withdraw_amount":
        amount = int(update.message.text)
        num = ctx.user_data["num"]

        res = sb.rpc("request_shop_withdrawal", {
            "p_number": num,
            "p_amount": amount
        }).execute()

        if not res.data.get("success"):
            await update.message.reply_text("❌ Erreur retrait")
            return

        await update.message.reply_text(
            f"✅ Retrait demandé\nFrais: {res.data['fees']}\nNet: {res.data['net']}"
        )

        ctx.user_data.clear()

# ─────────────────────────────
# ROUTER
# ─────────────────────────────
async def callbacks(update: Update, ctx):
    data = update.callback_query.data

    if data == "solde":
        await solde(update, ctx)
    elif data == "shop":
        await retrait_shop(update, ctx)

# ─────────────────────────────
# MAIN
# ─────────────────────────────
def main():
    keep_alive()  # ✅ KEEP ALIVE

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot lancé")
    app.run_polling()

if __name__ == "__main__":
    main()
