"""
bot.py — Bot Telegram utilisateur MindCash
Compatible avec le site web (thème vert, boutique accessible à tous)
Bibliothèque : python-telegram-bot >= 20.x
""""""
bot.py — Bot Telegram utilisateur MindCash
Compatible avec le site web (thème vert, boutique accessible à tous)
Bibliothèque : python-telegram-bot >= 20.x
"""

import os
import sys
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "").strip()
SUPABASE_URL   = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
ADMIN_CHAT_IDS = [int(x) for x in os.getenv("ADMIN_CHAT_IDS", "").split(",") if x.strip()]

# ── Validation au démarrage ──────────────────────────────────────────────────
missing = []
if not BOT_TOKEN:
    missing.append("BOT_TOKEN")
if not SUPABASE_URL:
    missing.append("SUPABASE_URL")
if not SUPABASE_KEY:
    missing.append("SUPABASE_SERVICE_KEY")

if missing:
    print(f"❌ ERREUR : Variables d'environnement manquantes : {', '.join(missing)}")
    print("👉 Vérifiez vos variables dans le dashboard Render > Environment")
    sys.exit(1)

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Connexion Supabase OK")

# Constantes identiques au site
DEPOT_MIN     = 5000
RETRAIT_MIN   = 4450
FRAIS_PERCENT = 5
BONUS_N1      = 2050
BONUS_N2      = 750
SHOP_MIN      = 2500
SHOP_FEE      = 3

# ConversationHandler states
(
    PHONE, PASSWORD, CONFIRM_PASSWORD, REF_CODE,
    DEPOT_NUM, DEPOT_MT,
    RETRAIT_NUM, RETRAIT_MT,
    SHOP_DEPOSIT_NUM, SHOP_DEPOSIT_MT,
) = range(10)

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def fmt(n: int) -> str:
    """Formatage FCFA avec séparateur de milliers"""
    return f"{n:,}".replace(",", " ")

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def depot_ouvert() -> bool:
    h = datetime.now().hour
    return 6 <= h < 22

def retrait_ouvert() -> bool:
    now = datetime.now()
    return now.weekday() < 5 and 7 <= now.hour < 17

async def get_user_by_tg(tg_id: int):
    """Récupère un user par son telegram_id"""
    res = sb.table("users").select("*").eq("telegram_id", tg_id).maybe_single().execute()
    return res.data

async def get_user_by_phone(phone: str):
    """Récupère un user par son numéro de téléphone"""
    res = sb.table("users").select("*").eq("phone", phone).maybe_single().execute()
    return res.data

def main_menu_kb(is_active: bool) -> InlineKeyboardMarkup:
    """Clavier principal selon statut du compte"""
    buttons = []
    if is_active:
        buttons += [
            [InlineKeyboardButton("💰 Mon solde",       callback_data="solde"),
             InlineKeyboardButton("📊 Statistiques",    callback_data="stats")],
            [InlineKeyboardButton("📥 Dépôt",           callback_data="depot"),
             InlineKeyboardButton("💳 Retrait",         callback_data="retrait")],
            [InlineKeyboardButton("🎁 Bonus du jour",   callback_data="bonus"),
             InlineKeyboardButton("👥 Parrainage",      callback_data="parrainage")],
            [InlineKeyboardButton("🛒 Boutique",        callback_data="boutique"),
             InlineKeyboardButton("📋 Historique",      callback_data="historique")],
        ]
    else:
        buttons += [
            [InlineKeyboardButton("🔓 Activer mon compte", callback_data="depot")],
            [InlineKeyboardButton("🛒 Voir la boutique",   callback_data="boutique")],
            [InlineKeyboardButton("📊 Mon profil",          callback_data="profil")],
        ]
    buttons.append([InlineKeyboardButton("❓ Aide",    callback_data="aide")])
    return InlineKeyboardMarkup(buttons)

# ──────────────────────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    user  = await get_user_by_tg(tg_id)
    if user:
        status = "✅ Actif" if user["is_active"] else "⏳ En attente d'activation"
        await update.message.reply_text(
            f"💸 *Bienvenue sur MindCash !*\n\n"
            f"👤 {user['name']}\n"
            f"🆔 {user['ref_code']}\n"
            f"📊 Statut : {status}\n"
            f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user["is_active"])
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Créer un compte", callback_data="register"),
             InlineKeyboardButton("🔑 Se connecter",    callback_data="login")],
        ])
        await update.message.reply_text(
            "💸 *Bienvenue sur MindCash !*\n\n"
            "Gagnez de l'argent chaque jour grâce aux tâches, publicités et parrainage.\n\n"
            "Créez votre compte ou connectez-vous pour commencer.",
            parse_mode="Markdown",
            reply_markup=kb
        )

# ──────────────────────────────────────────────────────────────────────────────
# INSCRIPTION
# ──────────────────────────────────────────────────────────────────────────────
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📝 *Inscription — Étape 1/4*\n\nEntrez votre nom complet :",
        parse_mode="Markdown"
    )
    ctx.user_data["reg_step"] = "name"

async def handle_registration_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("reg_step")
    text = update.message.text.strip()

    if step == "name":
        ctx.user_data["reg_name"] = text
        ctx.user_data["reg_step"] = "phone"
        await update.message.reply_text("📱 Entrez votre numéro de téléphone (0XXXXXXXXX) :")

    elif step == "phone":
        ctx.user_data["reg_phone"] = text
        ctx.user_data["reg_step"] = "password"
        await update.message.reply_text("🔑 Choisissez un mot de passe (min. 6 caractères) :")

    elif step == "password":
        if len(text) < 6:
            await update.message.reply_text("❌ Le mot de passe doit faire au moins 6 caractères. Réessayez :")
            return
        ctx.user_data["reg_pass"] = text
        ctx.user_data["reg_step"] = "ref"
        await update.message.reply_text(
            "👥 Code parrain (facultatif)\nEntrez le code ou tapez /skip pour ignorer :"
        )

    elif step == "ref":
        await finalize_register(update, ctx, ref=text)
        ctx.user_data.pop("reg_step", None)

async def cmd_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("reg_step") == "ref":
        await finalize_register(update, ctx, ref=None)
        ctx.user_data.pop("reg_step", None)

async def finalize_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE, ref):
    name  = ctx.user_data.get("reg_name", "")
    phone = ctx.user_data.get("reg_phone", "")
    pw    = ctx.user_data.get("reg_pass", "")
    tg_id = update.effective_user.id

    # Vérifier si le numéro existe déjà
    existing = await get_user_by_phone(phone)
    if existing:
        await update.message.reply_text("❌ Ce numéro de téléphone est déjà utilisé.")
        return

    # Résoudre le parrain
    referred_by = None
    if ref and ref != "/skip":
        pr = sb.table("users").select("id").eq("ref_code", ref.upper()).maybe_single().execute()
        if pr.data:
            referred_by = pr.data["id"]
        else:
            await update.message.reply_text("⚠️ Code parrain invalide, compte créé sans parrain.")

    import random, string
    ref_code = "MC-" + str(random.randint(100000, 999999))

    # Créer l'auth Supabase
    try:
        auth_res = sb.auth.admin.create_user({
            "email":    phone + "@mindcash.app",
            "password": pw,
            "email_confirm": True
        })
        uid = auth_res.user.id
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur création compte : {e}")
        return

    # Insérer dans users
    sb.table("users").insert({
        "id":           uid,
        "name":         name,
        "phone":        phone,
        "balance":      0,
        "is_active":    False,
        "ref_code":     ref_code,
        "referred_by":  referred_by,
        "telegram_id":  tg_id,
    }).execute()

    await update.message.reply_text(
        f"✅ *Compte créé avec succès !*\n\n"
        f"👤 {name}\n🆔 {ref_code}\n\n"
        f"Pour accéder à toutes les fonctionnalités, effectuez un dépôt d'activation de *5 000 FCFA minimum*.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(False)
    )

# ──────────────────────────────────────────────────────────────────────────────
# CONNEXION — lier Telegram à un compte existant
# ──────────────────────────────────────────────────────────────────────────────
async def cb_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔑 *Connexion*\n\nEntrez votre numéro de téléphone :",
        parse_mode="Markdown"
    )
    ctx.user_data["login_step"] = "phone"

async def handle_login_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("login_step")
    text = update.message.text.strip()

    if step == "phone":
        ctx.user_data["login_phone"] = text
        ctx.user_data["login_step"]  = "password"
        await update.message.reply_text("🔑 Entrez votre mot de passe :")

    elif step == "password":
        phone = ctx.user_data.get("login_phone", "")
        # Vérifier via Supabase auth
        try:
            sb.auth.sign_in_with_password({"email": phone + "@mindcash.app", "password": text})
        except Exception:
            await update.message.reply_text("❌ Téléphone ou mot de passe incorrect.")
            ctx.user_data.pop("login_step", None)
            return

        # Lier le telegram_id
        tg_id = update.effective_user.id
        sb.table("users").update({"telegram_id": tg_id}).eq("phone", phone).execute()
        user = await get_user_by_phone(phone)
        ctx.user_data.pop("login_step", None)

        await update.message.reply_text(
            f"✅ *Connecté !*\n\n"
            f"👤 {user['name']}\n🆔 {user['ref_code']}\n"
            f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user["is_active"])
        )

# ──────────────────────────────────────────────────────────────────────────────
# SOLDE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_solde(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start")
        return

    deps = sb.table("deposits").select("amount").eq("user_id", user["id"]).eq("status", "success").execute()
    total_depose = sum(d["amount"] for d in (deps.data or []))

    rets_p = sb.table("withdrawals").select("amount").eq("user_id", user["id"]).eq("status", "pending").execute()
    pending = sum(r["amount"] for r in (rets_p.data or []))

    shop_bal = user.get("shop_balance", 0) or 0

    await query.message.reply_text(
        f"💰 *Solde MindCash*\n\n"
        f"✅ Solde disponible : *{fmt(user.get('balance', 0))} FCFA*\n"
        f"📥 Total déposé : {fmt(total_depose)} FCFA\n"
        f"⏳ Retraits en attente : {fmt(pending)} FCFA\n"
        f"🛒 Solde boutique : {fmt(shop_bal)} FCFA",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Dépôt", callback_data="depot"),
             InlineKeyboardButton("💳 Retrait", callback_data="retrait")],
            [InlineKeyboardButton("🏠 Menu", callback_data="menu")],
        ])
    )

# ──────────────────────────────────────────────────────────────────────────────
# DÉPÔT D'ACTIVATION
# ──────────────────────────────────────────────────────────────────────────────
async def cb_depot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start")
        return
    if user.get("is_active"):
        await query.message.reply_text("✅ Votre compte est déjà actif !")
        return
    if not depot_ouvert():
        await query.message.reply_text("⏰ Les dépôts sont fermés. Ouverts de 6h à 22h.")
        return

    await query.message.reply_text(
        "📥 *Dépôt d'activation*\n\n"
        "🟡 Opérateur : *MTN MoMo uniquement*\n"
        "⚠️ Le nom qui doit apparaître lors du paiement : *CECILE CELINE*\n\n"
        f"Montant minimum : *{fmt(DEPOT_MIN)} FCFA*\n\n"
        "Entrez votre numéro MTN MoMo :",
        parse_mode="Markdown"
    )
    ctx.user_data["depot_step"] = "num"

async def handle_depot_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("depot_step")
    text = update.message.text.strip()

    if step == "num":
        ctx.user_data["depot_num"] = text
        ctx.user_data["depot_step"] = "mt"
        await update.message.reply_text(f"💰 Entrez le montant en FCFA (minimum {fmt(DEPOT_MIN)}) :")

    elif step == "mt":
        try:
            mt = int(text)
        except ValueError:
            await update.message.reply_text("❌ Montant invalide. Entrez un nombre entier :")
            return
        if mt < DEPOT_MIN:
            await update.message.reply_text(f"❌ Minimum {fmt(DEPOT_MIN)} FCFA. Réessayez :")
            return

        num   = ctx.user_data.get("depot_num", "")
        tg_id = update.effective_user.id
        user  = await get_user_by_tg(tg_id)
        ctx.user_data.pop("depot_step", None)

        try:
            res = sb.rpc("create_activation_deposit", {"p_number": num, "p_amount": mt}).execute()
            if not res.data or not res.data.get("success"):
                await update.message.reply_text(f"❌ Erreur : {res.data.get('message', 'Inconnue')}")
                return
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur inattendue : {e}")
            return

        await update.message.reply_text(
            f"✅ *Dépôt enregistré !*\n\n"
            f"📱 Numéro MTN : {num}\n"
            f"💰 Montant : {fmt(mt)} FCFA\n\n"
            f"*Instructions de paiement :*\n"
            f"1. Composez `*105#` sur votre téléphone\n"
            f"2. Choisissez l'option `6`\n"
            f"3. Code : `168694`\n"
            f"4. Montant : `{mt}`\n"
            f"5. Raison : `activation compte`\n"
            f"6. Confirmez avec votre code secret MTN\n\n"
            f"⚠️ Le nom qui doit apparaître : *CECILE CELINE*\n\n"
            f"L'administrateur validera votre dépôt et activera votre compte.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ])
        )

        for admin_id in ADMIN_CHAT_IDS:
            try:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Valider", callback_data=f"admin_val_dep_{user['id']}_{mt}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"admin_rej_dep_{user['id']}")],
                ])
                await ctx.bot.send_message(
                    admin_id,
                    f"🔔 *DÉPÔT D'ACTIVATION EN ATTENTE*\n\n"
                    f"👤 {user['name']}\n📞 {user['phone']}\n🆔 {user['ref_code']}\n"
                    f"💰 *{fmt(mt)} FCFA*\n📱 MTN MoMo · {num}",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# RETRAIT
# ──────────────────────────────────────────────────────────────────────────────
async def cb_retrait(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start"); return
    if not user.get("is_active"):
        await query.message.reply_text("❌ Votre compte n'est pas encore activé."); return
    if not retrait_ouvert():
        await query.message.reply_text("⏰ Retraits disponibles Lun–Ven 7h–17h."); return

    solde = user.get("balance", 0)
    if solde < RETRAIT_MIN:
        await query.message.reply_text(
            f"❌ Solde insuffisant.\n"
            f"💰 Solde actuel : {fmt(solde)} FCFA\n"
            f"📉 Minimum : {fmt(RETRAIT_MIN)} FCFA"
        )
        return

    await query.message.reply_text(
        f"💳 *Retrait MTN MoMo*\n\n"
        f"💰 Solde disponible : *{fmt(solde)} FCFA*\n"
        f"📉 Minimum : {fmt(RETRAIT_MIN)} FCFA\n"
        f"💸 Frais : {FRAIS_PERCENT}%\n\n"
        "Entrez votre numéro MTN MoMo :",
        parse_mode="Markdown"
    )
    ctx.user_data["retrait_step"] = "num"

async def handle_retrait_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("retrait_step")
    text = update.message.text.strip()

    if step == "num":
        ctx.user_data["retrait_num"] = text
        ctx.user_data["retrait_step"] = "mt"
        await update.message.reply_text(f"💰 Montant à retirer (minimum {fmt(RETRAIT_MIN)} FCFA) :")

    elif step == "mt":
        try:
            mt = int(text)
        except ValueError:
            await update.message.reply_text("❌ Montant invalide :"); return
        if mt < RETRAIT_MIN:
            await update.message.reply_text(f"❌ Minimum {fmt(RETRAIT_MIN)} FCFA :"); return

        num   = ctx.user_data.get("retrait_num", "")
        tg_id = update.effective_user.id
        user  = await get_user_by_tg(tg_id)
        ctx.user_data.pop("retrait_step", None)

        try:
            res = sb.rpc("request_withdrawal", {"p_number": num, "p_amount": mt}).execute()
            if not res.data or not res.data.get("success"):
                await update.message.reply_text(f"❌ {res.data.get('message', 'Erreur retrait')}"); return
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}"); return

        fees = res.data.get("fees", round(mt * FRAIS_PERCENT / 100))
        net  = res.data.get("net",  mt - fees)

        await update.message.reply_text(
            f"✅ *Retrait soumis !*\n\n"
            f"📱 Numéro : {num}\n"
            f"💰 Montant demandé : {fmt(mt)} FCFA\n"
            f"💸 Frais ({FRAIS_PERCENT}%) : {fmt(fees)} FCFA\n"
            f"✅ Vous recevrez : *{fmt(net)} FCFA*\n\n"
            f"Traitement sous 24h.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
        )

        for admin_id in ADMIN_CHAT_IDS:
            try:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Valider", callback_data=f"admin_val_ret_{user['id']}_{mt}_{num}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"admin_rej_ret_{user['id']}")],
                ])
                await ctx.bot.send_message(
                    admin_id,
                    f"💳 *DEMANDE DE RETRAIT*\n\n"
                    f"👤 {user['name']}\n📞 {user['phone']}\n🆔 {user['ref_code']}\n"
                    f"💰 {fmt(mt)} FCFA · Frais {fmt(fees)} FCFA · Net *{fmt(net)} FCFA*\n📱 {num}",
                    parse_mode="Markdown", reply_markup=kb
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# BONUS QUOTIDIEN
# ──────────────────────────────────────────────────────────────────────────────
async def cb_bonus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user or not user.get("is_active"):
        await query.message.reply_text("❌ Compte non actif."); return

    try:
        res = sb.rpc("claim_bonus_daily").execute()
        if not res.data or not res.data.get("success"):
            await query.message.reply_text(
                f"⏰ {res.data.get('message', 'Bonus déjà récupéré aujourd\'hui !')}"
            )
            return
        gain = res.data.get("gain", 20)
        await query.message.reply_text(
            f"🎁 *Bonus quotidien récupéré !*\n\n+{fmt(gain)} FCFA crédités sur votre compte.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Mon solde", callback_data="solde")]])
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Erreur : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# PARRAINAGE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_parrainage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    n1 = sb.table("users").select("id,name,is_active").eq("referred_by", user["id"]).execute().data or []
    gains_n1 = sum(BONUS_N1 for u in n1 if u.get("is_active"))

    n2_total, gains_n2 = 0, 0
    for u1 in n1:
        sub = sb.table("users").select("id,is_active").eq("referred_by", u1["id"]).execute().data or []
        n2_total += len(sub)
        gains_n2 += sum(BONUS_N2 for u2 in sub if u2.get("is_active"))

    link = f"https://cashmind.pages.dev/?ref={user['ref_code']}"
    msg  = (
        f"👥 *Parrainage MindCash*\n\n"
        f"🔗 Votre lien :\n`{link}`\n\n"
        f"📊 *Structure de rémunération :*\n"
        f"• Niveau 1 (direct) : *{fmt(BONUS_N1)} FCFA* par filleul\n"
        f"• Niveau 2 (indirect) : *{fmt(BONUS_N2)} FCFA* par filleul\n\n"
        f"📈 *Vos statistiques :*\n"
        f"• Filleuls N1 : {len(n1)} · Gains : {fmt(gains_n1)} FCFA\n"
        f"• Filleuls N2 : {n2_total} · Gains : {fmt(gains_n2)} FCFA\n\n"
        f"_Les gains sont crédités dès qu'un filleul active son compte._"
    )
    await query.message.reply_text(msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ──────────────────────────────────────────────────────────────────────────────
# BOUTIQUE — Accessible à tous (activé ou non)
# ──────────────────────────────────────────────────────────────────────────────
async def cb_boutique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start"); return

    is_active = user.get("is_active", False)
    products  = sb.table("products").select("*").order("created_at", desc=True).limit(10).execute().data or []

    if not products:
        await query.message.reply_text("🛒 Aucun produit disponible pour l'instant.")
        return

    notice = "" if is_active else "\n⚠️ _Compte non activé — vous pouvez voir les produits mais l'achat requiert un compte actif._\n"

    text = f"🛒 *Boutique MindCash*{notice}\n\n"
    buttons = []
    for p in products[:8]:
        text += f"📦 *{p['title']}*\n💰 {fmt(p.get('price', 0))} FCFA\n\n"
        if is_active:
            buttons.append([InlineKeyboardButton(
                f"🛍 Acheter — {p['title'][:20]}",
                callback_data=f"buy_{p['id']}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                f"🔒 {p['title'][:20]} — Activer pour acheter",
                callback_data="depot"
            )])

    buttons.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await query.message.reply_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_buy_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("buy_", "")
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user or not user.get("is_active"):
        await query.message.reply_text("❌ Activez votre compte pour acheter."); return

    try:
        res = sb.rpc("buy_product", {"p_product_id": product_id}).execute()
        if not res.data or not res.data.get("success"):
            await query.message.reply_text(f"❌ {res.data.get('message', 'Solde boutique insuffisant')}"); return
        product = sb.table("products").select("title,link").eq("id", product_id).maybe_single().execute().data
        await query.message.reply_text(
            f"✅ *Achat réussi !*\n\n"
            f"📦 {product.get('title', 'Produit')}\n"
            f"🔗 Lien d'accès : {product.get('link', '—')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Erreur : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# HISTORIQUE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_historique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    txs = sb.table("transactions").select("*").eq("user_id", user["id"])\
        .order("created_at", desc=True).limit(10).execute().data or []

    if not txs:
        await query.message.reply_text("📋 Aucune transaction pour l'instant."); return

    lbl = {"deposit": "Dépôt", "withdraw": "Retrait", "bonus": "Bonus",
           "ad": "Publicité", "mission": "Mission", "referral": "Parrainage"}
    text = "📋 *Transactions récentes*\n\n"
    for tx in txs:
        sign   = "+" if tx["type"] != "withdraw" else "−"
        status = "✅" if tx["status"] == "success" else ("⏳" if tx["status"] == "pending" else "❌")
        date   = tx["created_at"][:10]
        text  += f"{status} {lbl.get(tx['type'], tx['type'])} · {sign}{fmt(tx['amount'])} FCFA · {date}\n"

    await query.message.reply_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ──────────────────────────────────────────────────────────────────────────────
# STATS / PROFIL
# ──────────────────────────────────────────────────────────────────────────────
async def cb_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    gains_rows = sb.table("transactions").select("amount").eq("user_id", user["id"])\
        .in_("type", ["bonus", "ad", "mission", "referral"]).eq("status", "success").execute().data or []
    total_gagne = sum(r["amount"] for r in gains_rows)

    rets_ok = sb.table("withdrawals").select("amount").eq("user_id", user["id"]).eq("status", "success").execute().data or []
    total_retire = sum(r["amount"] for r in rets_ok)

    n1 = sb.table("users").select("id").eq("referred_by", user["id"]).execute().data or []
    missions = sb.table("completed_missions").select("id").eq("user_id", user["id"]).execute().data or []

    status = "✅ Actif" if user.get("is_active") else "⏳ En attente"
    await query.message.reply_text(
        f"📊 *Statistiques de {user['name']}*\n\n"
        f"🆔 {user['ref_code']}\n"
        f"📊 Statut : {status}\n"
        f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*\n"
        f"🏆 Total gagné : {fmt(total_gagne)} FCFA\n"
        f"💸 Total retiré : {fmt(total_retire)} FCFA\n"
        f"👥 Filleuls directs : {len(n1)}\n"
        f"✅ Missions complétées : {len(missions)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
    )

# ──────────────────────────────────────────────────────────────────────────────
# AIDE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_aide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "❓ *Aide MindCash*\n\n"
        "🔓 *Activation* : Déposez 5 000 FCFA minimum via MTN MoMo\n"
        "🎁 *Bonus* : +20 FCFA par jour (toutes les 24h)\n"
        "📥 *Dépôt* : Tous les jours de 6h à 22h\n"
        "💳 *Retrait* : Lundi–Vendredi de 7h à 17h (min. 4 450 FCFA)\n"
        "👥 *Parrainage N1* : 2 050 FCFA par filleul actif\n"
        "👥 *Parrainage N2* : 750 FCFA par filleul indirect\n"
        "🛒 *Boutique* : Accessible à tous (achat réservé aux comptes actifs)\n\n"
        "💸 Frais de retrait : 5%\n\n"
        "Pour toute question, contactez l'administrateur.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
    )

# ──────────────────────────────────────────────────────────────────────────────
# MENU (retour)
# ──────────────────────────────────────────────────────────────────────────────
async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("Utilisez /start"); return
    await query.message.reply_text(
        f"🏠 *Menu principal*\n\n👤 {user['name']} · {user['ref_code']}",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user.get("is_active", False))
    )

# ──────────────────────────────────────────────────────────────────────────────
# ROUTEUR MESSAGES (inscription / connexion / dépôt / retrait)
# ──────────────────────────────────────────────────────────────────────────────
async def route_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("reg_step")
    if step:
        await handle_registration_message(update, ctx); return

    step = ctx.user_data.get("login_step")
    if step:
        await handle_login_message(update, ctx); return

    step = ctx.user_data.get("depot_step")
    if step:
        await handle_depot_message(update, ctx); return

    step = ctx.user_data.get("retrait_step")
    if step:
        await handle_retrait_message(update, ctx); return

    await update.message.reply_text(
        "Utilisez /start pour accéder au menu principal."
    )

# ──────────────────────────────────────────────────────────────────────────────
# ROUTEUR CALLBACKS
# ──────────────────────────────────────────────────────────────────────────────
async def route_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    routes = {
        "register":   cb_register,
        "login":      cb_login,
        "solde":      cb_solde,
        "depot":      cb_depot,
        "retrait":    cb_retrait,
        "bonus":      cb_bonus,
        "parrainage": cb_parrainage,
        "boutique":   cb_boutique,
        "historique": cb_historique,
        "stats":      cb_stats,
        "profil":     cb_stats,
        "aide":       cb_aide,
        "menu":       cb_menu,
    }

    if data in routes:
        await routes[data](update, ctx)
    elif data.startswith("buy_"):
        await cb_buy_product(update, ctx)
    elif data.startswith("admin_"):
        await handle_admin_callback(update, ctx)
    else:
        await query.answer("Action non reconnue")

# ──────────────────────────────────────────────────────────────────────────────
# ACTIONS ADMIN (validation dépôt / retrait)
# ──────────────────────────────────────────────────────────────────────────────
async def handle_admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ Accès refusé.")
        return

    data = query.data

    # Valider dépôt : admin_val_dep_{user_id}_{amount}
    if data.startswith("admin_val_dep_"):
        parts   = data.split("_")
        user_id = parts[3]
        amount  = int(parts[4])

        sb.table("users").update({"is_active": True}).eq("id", user_id).execute()
        sb.table("deposits").insert({
            "user_id": user_id, "amount": amount,
            "status": "success", "operator": "mtn_momo",
            "created_at": now_utc()
        }).execute()
        sb.table("transactions").insert({
            "user_id": user_id, "amount": amount, "type": "deposit",
            "status": "success", "created_at": now_utc()
        }).execute()

        # Créditer le parrain N1
        user = sb.table("users").select("*").eq("id", user_id).maybe_single().execute().data
        if user and user.get("referred_by"):
            ref1 = sb.table("users").select("*").eq("id", user["referred_by"]).maybe_single().execute().data
            if ref1:
                new_bal = (ref1.get("balance") or 0) + BONUS_N1
                sb.table("users").update({"balance": new_bal}).eq("id", ref1["id"]).execute()
                sb.table("transactions").insert({
                    "user_id": ref1["id"], "amount": BONUS_N1, "type": "referral",
                    "status": "success", "created_at": now_utc()
                }).execute()
                # Parrain N2
                if ref1.get("referred_by"):
                    ref2 = sb.table("users").select("*").eq("id", ref1["referred_by"]).maybe_single().execute().data
                    if ref2:
                        new_bal2 = (ref2.get("balance") or 0) + BONUS_N2
                        sb.table("users").update({"balance": new_bal2}).eq("id", ref2["id"]).execute()
                        sb.table("transactions").insert({
                            "user_id": ref2["id"], "amount": BONUS_N2, "type": "referral",
                            "status": "success", "created_at": now_utc()
                        }).execute()

        await query.message.edit_text(
            query.message.text + "\n\n✅ *VALIDÉ — Compte activé*", parse_mode="Markdown"
        )

        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    f"✅ *Votre dépôt a été validé !*\n\n"
                    f"💰 {fmt(amount)} FCFA crédité\n"
                    f"🎉 Votre compte est maintenant *ACTIF* !",
                    parse_mode="Markdown",
                    reply_markup=main_menu_kb(True)
                )
            except Exception:
                pass

    # Rejeter dépôt : admin_rej_dep_{user_id}
    elif data.startswith("admin_rej_dep_"):
        user_id = data.replace("admin_rej_dep_", "")
        sb.table("deposits").update({"status": "failed"})\
            .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + "\n\n❌ *REJETÉ*", parse_mode="Markdown"
        )
        user = sb.table("users").select("telegram_id").eq("id", user_id).maybe_single().execute().data
        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    "❌ Votre dépôt a été rejeté. Contactez l'administrateur."
                )
            except Exception:
                pass

    # Valider retrait : admin_val_ret_{user_id}_{amount}_{num}
    elif data.startswith("admin_val_ret_"):
        parts   = data.split("_")
        user_id = parts[3]
        amount  = int(parts[4])
        num     = parts[5] if len(parts) > 5 else "—"
        fees    = round(amount * FRAIS_PERCENT / 100)
        net     = amount - fees
        sb.table("withdrawals").update({"status": "success"})\
            .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + f"\n\n✅ *VALIDÉ — {fmt(net)} FCFA envoyé sur {num}*",
            parse_mode="Markdown"
        )
        user = sb.table("users").select("telegram_id,name").eq("id", user_id).maybe_single().execute().data
        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    f"✅ *Retrait validé !*\n\n"
                    f"💸 {fmt(net)} FCFA envoyé sur *{num}* via MTN MoMo.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # Rejeter retrait : admin_rej_ret_{user_id}
    elif data.startswith("admin_rej_ret_"):
        user_id = data.replace("admin_rej_ret_", "")
        user_data_row = sb.table("users").select("*").eq("id", user_id).maybe_single().execute().data
        if user_data_row:
            pending_rets = sb.table("withdrawals").select("amount")\
                .eq("user_id", user_id).eq("status", "pending").execute().data or []
            refund = sum(r["amount"] for r in pending_rets)
            new_bal = (user_data_row.get("balance") or 0) + refund
            sb.table("users").update({"balance": new_bal}).eq("id", user_id).execute()
            sb.table("withdrawals").update({"status": "failed"})\
                .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + "\n\n❌ *REJETÉ — Solde remboursé*", parse_mode="Markdown"
        )
        if user_data_row and user_data_row.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user_data_row["telegram_id"],
                    "❌ Votre demande de retrait a été rejetée. Votre solde a été remboursé."
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("skip",  cmd_skip))
    app.add_handler(CallbackQueryHandler(route_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))

    print("🚀 MindCash Bot démarré...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

import os
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_SERVICE_KEY", "")   # clé service_role
ADMIN_CHAT_IDS = [int(x) for x in os.getenv("ADMIN_CHAT_IDS", "").split(",") if x.strip()]

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Constantes identiques au site
DEPOT_MIN     = 5000
RETRAIT_MIN   = 4450
FRAIS_PERCENT = 5
BONUS_N1      = 2050
BONUS_N2      = 750
SHOP_MIN      = 2500
SHOP_FEE      = 3

# ConversationHandler states
(
    PHONE, PASSWORD, CONFIRM_PASSWORD, REF_CODE,
    DEPOT_NUM, DEPOT_MT,
    RETRAIT_NUM, RETRAIT_MT,
    SHOP_DEPOSIT_NUM, SHOP_DEPOSIT_MT,
) = range(10)

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def fmt(n: int) -> str:
    """Formatage FCFA avec séparateur de milliers"""
    return f"{n:,}".replace(",", " ")

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def depot_ouvert() -> bool:
    h = datetime.now().hour
    return 6 <= h < 22

def retrait_ouvert() -> bool:
    now = datetime.now()
    return now.weekday() < 5 and 7 <= now.hour < 17

async def get_user_by_tg(tg_id: int):
    """Récupère un user par son telegram_id"""
    res = sb.table("users").select("*").eq("telegram_id", tg_id).maybe_single().execute()
    return res.data

async def get_user_by_phone(phone: str):
    """Récupère un user par son numéro de téléphone"""
    res = sb.table("users").select("*").eq("phone", phone).maybe_single().execute()
    return res.data

def main_menu_kb(is_active: bool) -> InlineKeyboardMarkup:
    """Clavier principal selon statut du compte"""
    buttons = []
    if is_active:
        buttons += [
            [InlineKeyboardButton("💰 Mon solde",       callback_data="solde"),
             InlineKeyboardButton("📊 Statistiques",    callback_data="stats")],
            [InlineKeyboardButton("📥 Dépôt",           callback_data="depot"),
             InlineKeyboardButton("💳 Retrait",         callback_data="retrait")],
            [InlineKeyboardButton("🎁 Bonus du jour",   callback_data="bonus"),
             InlineKeyboardButton("👥 Parrainage",      callback_data="parrainage")],
            [InlineKeyboardButton("🛒 Boutique",        callback_data="boutique"),
             InlineKeyboardButton("📋 Historique",      callback_data="historique")],
        ]
    else:
        buttons += [
            [InlineKeyboardButton("🔓 Activer mon compte", callback_data="depot")],
            # ✅ Boutique accessible même sans activation
            [InlineKeyboardButton("🛒 Voir la boutique",   callback_data="boutique")],
            [InlineKeyboardButton("📊 Mon profil",          callback_data="profil")],
        ]
    buttons.append([InlineKeyboardButton("❓ Aide",    callback_data="aide")])
    return InlineKeyboardMarkup(buttons)

# ──────────────────────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    user  = await get_user_by_tg(tg_id)
    if user:
        status = "✅ Actif" if user["is_active"] else "⏳ En attente d'activation"
        await update.message.reply_text(
            f"💸 *Bienvenue sur MindCash !*\n\n"
            f"👤 {user['name']}\n"
            f"🆔 {user['ref_code']}\n"
            f"📊 Statut : {status}\n"
            f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user["is_active"])
        )
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Créer un compte", callback_data="register"),
             InlineKeyboardButton("🔑 Se connecter",    callback_data="login")],
        ])
        await update.message.reply_text(
            "💸 *Bienvenue sur MindCash !*\n\n"
            "Gagnez de l'argent chaque jour grâce aux tâches, publicités et parrainage.\n\n"
            "Créez votre compte ou connectez-vous pour commencer.",
            parse_mode="Markdown",
            reply_markup=kb
        )

# ──────────────────────────────────────────────────────────────────────────────
# INSCRIPTION
# ──────────────────────────────────────────────────────────────────────────────
async def cb_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📝 *Inscription — Étape 1/4*\n\nEntrez votre nom complet :",
        parse_mode="Markdown"
    )
    ctx.user_data["reg_step"] = "name"
    return ConversationHandler.END   # géré via message handler

async def handle_registration_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("reg_step")
    text = update.message.text.strip()

    if step == "name":
        ctx.user_data["reg_name"] = text
        ctx.user_data["reg_step"] = "phone"
        await update.message.reply_text("📱 Entrez votre numéro de téléphone (0XXXXXXXXX) :")

    elif step == "phone":
        ctx.user_data["reg_phone"] = text
        ctx.user_data["reg_step"] = "password"
        await update.message.reply_text("🔑 Choisissez un mot de passe (min. 6 caractères) :")

    elif step == "password":
        if len(text) < 6:
            await update.message.reply_text("❌ Le mot de passe doit faire au moins 6 caractères. Réessayez :")
            return
        ctx.user_data["reg_pass"] = text
        ctx.user_data["reg_step"] = "ref"
        await update.message.reply_text(
            "👥 Code parrain (facultatif)\nEntrez le code ou tapez /skip pour ignorer :"
        )

    elif step == "ref":
        await finalize_register(update, ctx, ref=text)
        ctx.user_data.pop("reg_step", None)

async def cmd_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("reg_step") == "ref":
        await finalize_register(update, ctx, ref=None)
        ctx.user_data.pop("reg_step", None)

async def finalize_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE, ref):
    name  = ctx.user_data.get("reg_name", "")
    phone = ctx.user_data.get("reg_phone", "")
    pw    = ctx.user_data.get("reg_pass", "")
    tg_id = update.effective_user.id

    # Vérifier si le numéro existe déjà
    existing = await get_user_by_phone(phone)
    if existing:
        await update.message.reply_text("❌ Ce numéro de téléphone est déjà utilisé.")
        return

    # Résoudre le parrain
    referred_by = None
    if ref and ref != "/skip":
        pr = sb.table("users").select("id").eq("ref_code", ref.upper()).maybe_single().execute()
        if pr.data:
            referred_by = pr.data["id"]
        else:
            await update.message.reply_text("⚠️ Code parrain invalide, compte créé sans parrain.")

    import random, string
    ref_code = "MC-" + str(random.randint(100000, 999999))

    # Créer l'auth Supabase
    try:
        auth_res = sb.auth.admin.create_user({
            "email":    phone + "@mindcash.app",
            "password": pw,
            "email_confirm": True
        })
        uid = auth_res.user.id
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur création compte : {e}")
        return

    # Insérer dans users
    sb.table("users").insert({
        "id":           uid,
        "name":         name,
        "phone":        phone,
        "balance":      0,
        "is_active":    False,
        "ref_code":     ref_code,
        "referred_by":  referred_by,
        "telegram_id":  tg_id,
    }).execute()

    await update.message.reply_text(
        f"✅ *Compte créé avec succès !*\n\n"
        f"👤 {name}\n🆔 {ref_code}\n\n"
        f"Pour accéder à toutes les fonctionnalités, effectuez un dépôt d'activation de *5 000 FCFA minimum*.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(False)
    )

# ──────────────────────────────────────────────────────────────────────────────
# CONNEXION — lier Telegram à un compte existant
# ──────────────────────────────────────────────────────────────────────────────
async def cb_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🔑 *Connexion*\n\nEntrez votre numéro de téléphone :",
        parse_mode="Markdown"
    )
    ctx.user_data["login_step"] = "phone"

async def handle_login_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("login_step")
    text = update.message.text.strip()

    if step == "phone":
        ctx.user_data["login_phone"] = text
        ctx.user_data["login_step"]  = "password"
        await update.message.reply_text("🔑 Entrez votre mot de passe :")

    elif step == "password":
        phone = ctx.user_data.get("login_phone", "")
        # Vérifier via Supabase auth
        try:
            sb.auth.sign_in_with_password({"email": phone + "@mindcash.app", "password": text})
        except Exception:
            await update.message.reply_text("❌ Téléphone ou mot de passe incorrect.")
            ctx.user_data.pop("login_step", None)
            return

        # Lier le telegram_id
        tg_id = update.effective_user.id
        sb.table("users").update({"telegram_id": tg_id}).eq("phone", phone).execute()
        user = await get_user_by_phone(phone)
        ctx.user_data.pop("login_step", None)

        await update.message.reply_text(
            f"✅ *Connecté !*\n\n"
            f"👤 {user['name']}\n🆔 {user['ref_code']}\n"
            f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*",
            parse_mode="Markdown",
            reply_markup=main_menu_kb(user["is_active"])
        )

# ──────────────────────────────────────────────────────────────────────────────
# SOLDE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_solde(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start")
        return

    # Dépôts totaux
    deps = sb.table("deposits").select("amount").eq("user_id", user["id"]).eq("status", "success").execute()
    total_depose = sum(d["amount"] for d in (deps.data or []))

    # Retraits en attente
    rets_p = sb.table("withdrawals").select("amount").eq("user_id", user["id"]).eq("status", "pending").execute()
    pending = sum(r["amount"] for r in (rets_p.data or []))

    shop_bal = user.get("shop_balance", 0) or 0

    await query.message.reply_text(
        f"💰 *Solde MindCash*\n\n"
        f"✅ Solde disponible : *{fmt(user.get('balance', 0))} FCFA*\n"
        f"📥 Total déposé : {fmt(total_depose)} FCFA\n"
        f"⏳ Retraits en attente : {fmt(pending)} FCFA\n"
        f"🛒 Solde boutique : {fmt(shop_bal)} FCFA",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Dépôt", callback_data="depot"),
             InlineKeyboardButton("💳 Retrait", callback_data="retrait")],
            [InlineKeyboardButton("🏠 Menu", callback_data="menu")],
        ])
    )

# ──────────────────────────────────────────────────────────────────────────────
# DÉPÔT D'ACTIVATION
# ──────────────────────────────────────────────────────────────────────────────
async def cb_depot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start")
        return
    if user.get("is_active"):
        await query.message.reply_text("✅ Votre compte est déjà actif !")
        return
    if not depot_ouvert():
        await query.message.reply_text("⏰ Les dépôts sont fermés. Ouverts de 6h à 22h.")
        return

    await query.message.reply_text(
        "📥 *Dépôt d'activation*\n\n"
        "🟡 Opérateur : *MTN MoMo uniquement*\n"
        "⚠️ Le nom qui doit apparaître lors du paiement : *CECILE CELINE*\n\n"
        f"Montant minimum : *{fmt(DEPOT_MIN)} FCFA*\n\n"
        "Entrez votre numéro MTN MoMo :",
        parse_mode="Markdown"
    )
    ctx.user_data["depot_step"] = "num"

async def handle_depot_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("depot_step")
    text = update.message.text.strip()

    if step == "num":
        ctx.user_data["depot_num"] = text
        ctx.user_data["depot_step"] = "mt"
        await update.message.reply_text(f"💰 Entrez le montant en FCFA (minimum {fmt(DEPOT_MIN)}) :")

    elif step == "mt":
        try:
            mt = int(text)
        except ValueError:
            await update.message.reply_text("❌ Montant invalide. Entrez un nombre entier :")
            return
        if mt < DEPOT_MIN:
            await update.message.reply_text(f"❌ Minimum {fmt(DEPOT_MIN)} FCFA. Réessayez :")
            return

        num   = ctx.user_data.get("depot_num", "")
        tg_id = update.effective_user.id
        user  = await get_user_by_tg(tg_id)
        ctx.user_data.pop("depot_step", None)

        # Appel RPC create_activation_deposit
        try:
            res = sb.rpc("create_activation_deposit", {"p_number": num, "p_amount": mt}).execute()
            if not res.data or not res.data.get("success"):
                await update.message.reply_text(f"❌ Erreur : {res.data.get('message', 'Inconnue')}")
                return
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur inattendue : {e}")
            return

        await update.message.reply_text(
            f"✅ *Dépôt enregistré !*\n\n"
            f"📱 Numéro MTN : {num}\n"
            f"💰 Montant : {fmt(mt)} FCFA\n\n"
            f"*Instructions de paiement :*\n"
            f"1. Composez `*105#` sur votre téléphone\n"
            f"2. Choisissez l'option `6`\n"
            f"3. Code : `168694`\n"
            f"4. Montant : `{mt}`\n"
            f"5. Raison : `activation compte`\n"
            f"6. Confirmez avec votre code secret MTN\n\n"
            f"⚠️ Le nom qui doit apparaître : *CECILE CELINE*\n\n"
            f"L'administrateur validera votre dépôt et activera votre compte.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Menu", callback_data="menu")]
            ])
        )

        # Notifier les admins
        for admin_id in ADMIN_CHAT_IDS:
            try:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Valider", callback_data=f"admin_val_dep_{user['id']}_{mt}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"admin_rej_dep_{user['id']}")],
                ])
                await ctx.bot.send_message(
                    admin_id,
                    f"🔔 *DÉPÔT D'ACTIVATION EN ATTENTE*\n\n"
                    f"👤 {user['name']}\n📞 {user['phone']}\n🆔 {user['ref_code']}\n"
                    f"💰 *{fmt(mt)} FCFA*\n📱 MTN MoMo · {num}",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# RETRAIT
# ──────────────────────────────────────────────────────────────────────────────
async def cb_retrait(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start"); return
    if not user.get("is_active"):
        await query.message.reply_text("❌ Votre compte n'est pas encore activé."); return
    if not retrait_ouvert():
        await query.message.reply_text("⏰ Retraits disponibles Lun–Ven 7h–17h."); return

    solde = user.get("balance", 0)
    if solde < RETRAIT_MIN:
        await query.message.reply_text(
            f"❌ Solde insuffisant.\n"
            f"💰 Solde actuel : {fmt(solde)} FCFA\n"
            f"📉 Minimum : {fmt(RETRAIT_MIN)} FCFA"
        )
        return

    await query.message.reply_text(
        f"💳 *Retrait MTN MoMo*\n\n"
        f"💰 Solde disponible : *{fmt(solde)} FCFA*\n"
        f"📉 Minimum : {fmt(RETRAIT_MIN)} FCFA\n"
        f"💸 Frais : {FRAIS_PERCENT}%\n\n"
        "Entrez votre numéro MTN MoMo :",
        parse_mode="Markdown"
    )
    ctx.user_data["retrait_step"] = "num"

async def handle_retrait_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("retrait_step")
    text = update.message.text.strip()

    if step == "num":
        ctx.user_data["retrait_num"] = text
        ctx.user_data["retrait_step"] = "mt"
        await update.message.reply_text(f"💰 Montant à retirer (minimum {fmt(RETRAIT_MIN)} FCFA) :")

    elif step == "mt":
        try:
            mt = int(text)
        except ValueError:
            await update.message.reply_text("❌ Montant invalide :"); return
        if mt < RETRAIT_MIN:
            await update.message.reply_text(f"❌ Minimum {fmt(RETRAIT_MIN)} FCFA :"); return

        num   = ctx.user_data.get("retrait_num", "")
        tg_id = update.effective_user.id
        user  = await get_user_by_tg(tg_id)
        ctx.user_data.pop("retrait_step", None)

        try:
            res = sb.rpc("request_withdrawal", {"p_number": num, "p_amount": mt}).execute()
            if not res.data or not res.data.get("success"):
                await update.message.reply_text(f"❌ {res.data.get('message', 'Erreur retrait')}"); return
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur : {e}"); return

        fees = res.data.get("fees", round(mt * FRAIS_PERCENT / 100))
        net  = res.data.get("net",  mt - fees)

        await update.message.reply_text(
            f"✅ *Retrait soumis !*\n\n"
            f"📱 Numéro : {num}\n"
            f"💰 Montant demandé : {fmt(mt)} FCFA\n"
            f"💸 Frais ({FRAIS_PERCENT}%) : {fmt(fees)} FCFA\n"
            f"✅ Vous recevrez : *{fmt(net)} FCFA*\n\n"
            f"Traitement sous 24h.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
        )

        for admin_id in ADMIN_CHAT_IDS:
            try:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Valider", callback_data=f"admin_val_ret_{user['id']}_{mt}_{num}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"admin_rej_ret_{user['id']}")],
                ])
                await ctx.bot.send_message(
                    admin_id,
                    f"💳 *DEMANDE DE RETRAIT*\n\n"
                    f"👤 {user['name']}\n📞 {user['phone']}\n🆔 {user['ref_code']}\n"
                    f"💰 {fmt(mt)} FCFA · Frais {fmt(fees)} FCFA · Net *{fmt(net)} FCFA*\n📱 {num}",
                    parse_mode="Markdown", reply_markup=kb
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# BONUS QUOTIDIEN
# ──────────────────────────────────────────────────────────────────────────────
async def cb_bonus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user or not user.get("is_active"):
        await query.message.reply_text("❌ Compte non actif."); return

    try:
        res = sb.rpc("claim_bonus_daily").execute()
        if not res.data or not res.data.get("success"):
            await query.message.reply_text(
                f"⏰ {res.data.get('message', 'Bonus déjà récupéré aujourd\'hui !')}"
            )
            return
        gain = res.data.get("gain", 20)
        await query.message.reply_text(
            f"🎁 *Bonus quotidien récupéré !*\n\n+{fmt(gain)} FCFA crédités sur votre compte.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Mon solde", callback_data="solde")]])
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Erreur : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# PARRAINAGE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_parrainage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    n1 = sb.table("users").select("id,name,is_active").eq("referred_by", user["id"]).execute().data or []
    gains_n1 = sum(BONUS_N1 for u in n1 if u.get("is_active"))

    n2_total, gains_n2 = 0, 0
    for u1 in n1:
        sub = sb.table("users").select("id,is_active").eq("referred_by", u1["id"]).execute().data or []
        n2_total += len(sub)
        gains_n2 += sum(BONUS_N2 for u2 in sub if u2.get("is_active"))

    link = f"https://cashmind.pages.dev/?ref={user['ref_code']}"
    msg  = (
        f"👥 *Parrainage MindCash*\n\n"
        f"🔗 Votre lien :\n`{link}`\n\n"
        f"📊 *Structure de rémunération :*\n"
        f"• Niveau 1 (direct) : *{fmt(BONUS_N1)} FCFA* par filleul\n"
        f"• Niveau 2 (indirect) : *{fmt(BONUS_N2)} FCFA* par filleul\n\n"
        f"📈 *Vos statistiques :*\n"
        f"• Filleuls N1 : {len(n1)} · Gains : {fmt(gains_n1)} FCFA\n"
        f"• Filleuls N2 : {n2_total} · Gains : {fmt(gains_n2)} FCFA\n\n"
        f"_Les gains sont crédités dès qu'un filleul active son compte._"
    )
    await query.message.reply_text(msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ──────────────────────────────────────────────────────────────────────────────
# BOUTIQUE — ✅ Accessible à tous (activé ou non)
# ──────────────────────────────────────────────────────────────────────────────
async def cb_boutique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié. Utilisez /start"); return

    is_active = user.get("is_active", False)
    products  = sb.table("products").select("*").order("created_at", desc=True).limit(10).execute().data or []

    if not products:
        await query.message.reply_text("🛒 Aucun produit disponible pour l'instant.")
        return

    notice = "" if is_active else "\n⚠️ _Compte non activé — vous pouvez voir les produits mais l'achat requiert un compte actif._\n"

    text = f"🛒 *Boutique MindCash*{notice}\n\n"
    buttons = []
    for p in products[:8]:
        text += f"📦 *{p['title']}*\n💰 {fmt(p.get('price', 0))} FCFA\n\n"
        if is_active:
            buttons.append([InlineKeyboardButton(
                f"🛍 Acheter — {p['title'][:20]}",
                callback_data=f"buy_{p['id']}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                f"🔒 {p['title'][:20]} — Activer pour acheter",
                callback_data="depot"
            )])

    buttons.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    await query.message.reply_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons))

async def cb_buy_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("buy_", "")
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user or not user.get("is_active"):
        await query.message.reply_text("❌ Activez votre compte pour acheter."); return

    try:
        res = sb.rpc("buy_product", {"p_product_id": product_id}).execute()
        if not res.data or not res.data.get("success"):
            await query.message.reply_text(f"❌ {res.data.get('message', 'Solde boutique insuffisant')}"); return
        product = sb.table("products").select("title,link").eq("id", product_id).maybe_single().execute().data
        await query.message.reply_text(
            f"✅ *Achat réussi !*\n\n"
            f"📦 {product.get('title', 'Produit')}\n"
            f"🔗 Lien d'accès : {product.get('link', '—')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Erreur : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# HISTORIQUE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_historique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    txs = sb.table("transactions").select("*").eq("user_id", user["id"])\
        .order("created_at", desc=True).limit(10).execute().data or []

    if not txs:
        await query.message.reply_text("📋 Aucune transaction pour l'instant."); return

    lbl = {"deposit": "Dépôt", "withdraw": "Retrait", "bonus": "Bonus",
           "ad": "Publicité", "mission": "Mission", "referral": "Parrainage"}
    text = "📋 *Transactions récentes*\n\n"
    for tx in txs:
        sign   = "+" if tx["type"] != "withdraw" else "−"
        status = "✅" if tx["status"] == "success" else ("⏳" if tx["status"] == "pending" else "❌")
        date   = tx["created_at"][:10]
        text  += f"{status} {lbl.get(tx['type'], tx['type'])} · {sign}{fmt(tx['amount'])} FCFA · {date}\n"

    await query.message.reply_text(text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))

# ──────────────────────────────────────────────────────────────────────────────
# STATS / PROFIL
# ──────────────────────────────────────────────────────────────────────────────
async def cb_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("❌ Compte non lié."); return

    gains_rows = sb.table("transactions").select("amount").eq("user_id", user["id"])\
        .in_("type", ["bonus", "ad", "mission", "referral"]).eq("status", "success").execute().data or []
    total_gagne = sum(r["amount"] for r in gains_rows)

    rets_ok = sb.table("withdrawals").select("amount").eq("user_id", user["id"]).eq("status", "success").execute().data or []
    total_retire = sum(r["amount"] for r in rets_ok)

    n1 = sb.table("users").select("id").eq("referred_by", user["id"]).execute().data or []
    missions = sb.table("completed_missions").select("id").eq("user_id", user["id"]).execute().data or []

    status = "✅ Actif" if user.get("is_active") else "⏳ En attente"
    await query.message.reply_text(
        f"📊 *Statistiques de {user['name']}*\n\n"
        f"🆔 {user['ref_code']}\n"
        f"📊 Statut : {status}\n"
        f"💰 Solde : *{fmt(user.get('balance', 0))} FCFA*\n"
        f"🏆 Total gagné : {fmt(total_gagne)} FCFA\n"
        f"💸 Total retiré : {fmt(total_retire)} FCFA\n"
        f"👥 Filleuls directs : {len(n1)}\n"
        f"✅ Missions complétées : {len(missions)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
    )

# ──────────────────────────────────────────────────────────────────────────────
# AIDE
# ──────────────────────────────────────────────────────────────────────────────
async def cb_aide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "❓ *Aide MindCash*\n\n"
        "🔓 *Activation* : Déposez 5 000 FCFA minimum via MTN MoMo\n"
        "🎁 *Bonus* : +20 FCFA par jour (toutes les 24h)\n"
        "📥 *Dépôt* : Tous les jours de 6h à 22h\n"
        "💳 *Retrait* : Lundi–Vendredi de 7h à 17h (min. 4 450 FCFA)\n"
        "👥 *Parrainage N1* : 2 050 FCFA par filleul actif\n"
        "👥 *Parrainage N2* : 750 FCFA par filleul indirect\n"
        "🛒 *Boutique* : Accessible à tous (achat réservé aux comptes actifs)\n\n"
        "💸 Frais de retrait : 5%\n\n"
        "Pour toute question, contactez l'administrateur.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]])
    )

# ──────────────────────────────────────────────────────────────────────────────
# MENU (retour)
# ──────────────────────────────────────────────────────────────────────────────
async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    user  = await get_user_by_tg(tg_id)
    if not user:
        await query.message.reply_text("Utilisez /start"); return
    await query.message.reply_text(
        f"🏠 *Menu principal*\n\n👤 {user['name']} · {user['ref_code']}",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(user.get("is_active", False))
    )

# ──────────────────────────────────────────────────────────────────────────────
# ROUTEUR MESSAGES (inscription / connexion / dépôt / retrait)
# ──────────────────────────────────────────────────────────────────────────────
async def route_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    step = ctx.user_data.get("reg_step")
    if step:
        await handle_registration_message(update, ctx); return

    step = ctx.user_data.get("login_step")
    if step:
        await handle_login_message(update, ctx); return

    step = ctx.user_data.get("depot_step")
    if step:
        await handle_depot_message(update, ctx); return

    step = ctx.user_data.get("retrait_step")
    if step:
        await handle_retrait_message(update, ctx); return

    # Message non reconnu
    await update.message.reply_text(
        "Utilisez /start pour accéder au menu principal."
    )

# ──────────────────────────────────────────────────────────────────────────────
# ROUTEUR CALLBACKS
# ──────────────────────────────────────────────────────────────────────────────
async def route_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    routes = {
        "register":   cb_register,
        "login":      cb_login,
        "solde":      cb_solde,
        "depot":      cb_depot,
        "retrait":    cb_retrait,
        "bonus":      cb_bonus,
        "parrainage": cb_parrainage,
        "boutique":   cb_boutique,
        "historique": cb_historique,
        "stats":      cb_stats,
        "profil":     cb_stats,
        "aide":       cb_aide,
        "menu":       cb_menu,
    }

    if data in routes:
        await routes[data](update, ctx)
    elif data.startswith("buy_"):
        await cb_buy_product(update, ctx)
    elif data.startswith("admin_"):
        await handle_admin_callback(update, ctx)
    else:
        await query.answer("Action non reconnue")

# ──────────────────────────────────────────────────────────────────────────────
# ACTIONS ADMIN (validation dépôt / retrait)
# ──────────────────────────────────────────────────────────────────────────────
async def handle_admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_CHAT_IDS:
        await query.message.reply_text("❌ Accès refusé.")
        return

    data = query.data

    # Valider dépôt : admin_val_dep_{user_id}_{amount}
    if data.startswith("admin_val_dep_"):
        parts   = data.split("_")
        user_id = parts[3]
        amount  = int(parts[4])
        # Activer le compte + créer la transaction
        sb.table("users").update({"is_active": True}).eq("id", user_id).execute()
        sb.table("deposits").insert({
            "user_id": user_id, "amount": amount,
            "status": "success", "operator": "mtn_momo",
            "created_at": now_utc()
        }).execute()
        sb.table("transactions").insert({
            "user_id": user_id, "amount": amount, "type": "deposit",
            "status": "success", "created_at": now_utc()
        }).execute()

        # Créditer le parrain N1
        user = sb.table("users").select("*").eq("id", user_id).maybe_single().execute().data
        if user and user.get("referred_by"):
            ref1 = sb.table("users").select("*").eq("id", user["referred_by"]).maybe_single().execute().data
            if ref1:
                new_bal = (ref1.get("balance") or 0) + BONUS_N1
                sb.table("users").update({"balance": new_bal}).eq("id", ref1["id"]).execute()
                sb.table("transactions").insert({
                    "user_id": ref1["id"], "amount": BONUS_N1, "type": "referral",
                    "status": "success", "created_at": now_utc()
                }).execute()
                # Parrain N2
                if ref1.get("referred_by"):
                    ref2 = sb.table("users").select("*").eq("id", ref1["referred_by"]).maybe_single().execute().data
                    if ref2:
                        new_bal2 = (ref2.get("balance") or 0) + BONUS_N2
                        sb.table("users").update({"balance": new_bal2}).eq("id", ref2["id"]).execute()
                        sb.table("transactions").insert({
                            "user_id": ref2["id"], "amount": BONUS_N2, "type": "referral",
                            "status": "success", "created_at": now_utc()
                        }).execute()

        await query.message.edit_text(
            query.message.text + "\n\n✅ *VALIDÉ — Compte activé*", parse_mode="Markdown"
        )

        # Notifier l'utilisateur
        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    f"✅ *Votre dépôt a été validé !*\n\n"
                    f"💰 {fmt(amount)} FCFA crédité\n"
                    f"🎉 Votre compte est maintenant *ACTIF* !",
                    parse_mode="Markdown",
                    reply_markup=main_menu_kb(True)
                )
            except Exception:
                pass

    # Rejeter dépôt : admin_rej_dep_{user_id}
    elif data.startswith("admin_rej_dep_"):
        user_id = data.replace("admin_rej_dep_", "")
        sb.table("deposits").update({"status": "failed"})\
            .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + "\n\n❌ *REJETÉ*", parse_mode="Markdown"
        )
        user = sb.table("users").select("telegram_id").eq("id", user_id).maybe_single().execute().data
        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    "❌ Votre dépôt a été rejeté. Contactez l'administrateur."
                )
            except Exception:
                pass

    # Valider retrait : admin_val_ret_{user_id}_{amount}_{num}
    elif data.startswith("admin_val_ret_"):
        parts   = data.split("_")
        user_id = parts[3]
        amount  = int(parts[4])
        num     = parts[5] if len(parts) > 5 else "—"
        fees    = round(amount * FRAIS_PERCENT / 100)
        net     = amount - fees
        sb.table("withdrawals").update({"status": "success"})\
            .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + f"\n\n✅ *VALIDÉ — {fmt(net)} FCFA envoyé sur {num}*",
            parse_mode="Markdown"
        )
        user = sb.table("users").select("telegram_id,name").eq("id", user_id).maybe_single().execute().data
        if user and user.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user["telegram_id"],
                    f"✅ *Retrait validé !*\n\n"
                    f"💸 {fmt(net)} FCFA envoyé sur *{num}* via MTN MoMo.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # Rejeter retrait : admin_rej_ret_{user_id}
    elif data.startswith("admin_rej_ret_"):
        user_id = data.replace("admin_rej_ret_", "")
        user_data_row = sb.table("users").select("*").eq("id", user_id).maybe_single().execute().data
        if user_data_row:
            # Rembourser
            pending_rets = sb.table("withdrawals").select("amount")\
                .eq("user_id", user_id).eq("status", "pending").execute().data or []
            refund = sum(r["amount"] for r in pending_rets)
            new_bal = (user_data_row.get("balance") or 0) + refund
            sb.table("users").update({"balance": new_bal}).eq("id", user_id).execute()
            sb.table("withdrawals").update({"status": "failed"})\
                .eq("user_id", user_id).eq("status", "pending").execute()
        await query.message.edit_text(
            query.message.text + "\n\n❌ *REJETÉ — Solde remboursé*", parse_mode="Markdown"
        )
        if user_data_row and user_data_row.get("telegram_id"):
            try:
                await ctx.bot.send_message(
                    user_data_row["telegram_id"],
                    "❌ Votre demande de retrait a été rejetée. Votre solde a été remboursé."
                )
            except Exception:
                pass

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("skip",  cmd_skip))

    # Callbacks
    app.add_handler(CallbackQueryHandler(route_callback))

    # Messages texte (routeur multi-étapes)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))

    print("🚀 MindCash Bot démarré...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
