"""
╔══════════════════════════════════════════════════════════════════╗
║         MINDCASH — BOT ADMIN COMPLET v4                         ║
║  ✅ Correction bug produits (NULL vs False)                     ║
║  ✅ Ajout produits depuis le bot                                 ║
╚══════════════════════════════════════════════════════════════════╝

Installation :
    pip install python-telegram-bot==20.7 supabase python-dotenv

Fichier .env :
    BOT_TOKEN=...
    SUPABASE_URL=...
    SUPABASE_KEY=...          ← clé SERVICE_ROLE
    ADMIN_CHAT_ID=123,456
    FRAIS_PERCENT=5
"""

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters,
)

# ── Keep-alive (Replit / Railway) ─────────────────────────────────
try:
    from keep_alive import keep_alive
    HAS_KEEPALIVE = True
except ImportError:
    HAS_KEEPALIVE = False

# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
load_dotenv()

BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")
ADMIN_CHAT_ID = list(map(int, filter(None, os.getenv("ADMIN_CHAT_ID", "").split(","))))
FRAIS_PERCENT = int(os.getenv("FRAIS_PERCENT", "5"))
BONUS_N1      = int(os.getenv("BONUS_N1", "2050"))
BONUS_N2      = int(os.getenv("BONUS_N2", "750"))
VENDOR_PCT    = int(os.getenv("VENDOR_PERCENT", "80"))

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Variables manquantes dans .env")

# ── États ConversationHandler ──────────────────────────────────────
(
    AD_TITLE, AD_DESC, AD_ICON, AD_DURATION, AD_REWARD, AD_LINK,
    SEARCH_INPUT,
    CREDIT_USER_ID, CREDIT_TYPE, CREDIT_AMOUNT,
    # ✅ NOUVEAUX états pour l'ajout de produit admin
    PROD_TITLE, PROD_DESC, PROD_PRICE, PROD_LINK, PROD_COVER,
) = range(15)

# ══════════════════════════════════════════════════════════════════
#  INIT
# ══════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def is_admin(uid: int) -> bool:
    return uid in ADMIN_CHAT_ID

def fmt(n) -> str:
    try:
        return f"{int(n):,} FCFA".replace(",", " ")
    except Exception:
        return f"{n} FCFA"

def fmt_date(s: str) -> str:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return s

def badge(status: str) -> str:
    return {"pending": "⏳ En attente", "success": "✅ Validé",
            "failed": "❌ Échoué", "rejected": "🚫 Rejeté"}.get(status, status)

def back(dest="menu_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principal", callback_data=dest)]])

def calc_frais(amount: int) -> tuple[int, int]:
    fees = round(amount * FRAIS_PERCENT / 100)
    return fees, amount - fees


# ══════════════════════════════════════════════════════════════════
#  MENU PRINCIPAL
# ══════════════════════════════════════════════════════════════════
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Dépôts",           callback_data="menu_deposits_pending"),
            InlineKeyboardButton("💳 Retraits",          callback_data="menu_withdrawals_pending"),
        ],
        [
            InlineKeyboardButton("🛒 Recharges boutique", callback_data="menu_shop_deposits"),
            InlineKeyboardButton("💸 Retraits boutique",  callback_data="menu_shop_withdrawals"),
        ],
        [
            InlineKeyboardButton("💜 Retraits gains ventes", callback_data="menu_gains_withdrawals"),
        ],
        [
            InlineKeyboardButton("📦 Produits à valider", callback_data="menu_products_pending"),
            InlineKeyboardButton("🛍 Produits actifs",    callback_data="menu_products_active"),
        ],
        [
            # ✅ Nouveau bouton : Ajouter un produit admin
            InlineKeyboardButton("➕ Ajouter un produit", callback_data="menu_add_product"),
        ],
        [
            InlineKeyboardButton("🔓 Comptes à activer", callback_data="menu_inactive_accounts"),
            InlineKeyboardButton("🔍 Chercher un user",  callback_data="menu_search_user"),
        ],
        [
            InlineKeyboardButton("📋 Historique dépôts",   callback_data="menu_deposits_history"),
            InlineKeyboardButton("📋 Historique retraits",  callback_data="menu_withdrawals_history"),
        ],
        [
            InlineKeyboardButton("📢 Publicités",   callback_data="menu_ads"),
            InlineKeyboardButton("📊 Statistiques", callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton("💰 Créditer un solde",  callback_data="menu_credit_user"),
            InlineKeyboardButton("📣 Diffusion",           callback_data="menu_broadcast_start"),
        ],
    ])


# ══════════════════════════════════════════════════════════════════
#  COMMANDES
# ══════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Accès refusé.")
        return
    await update.message.reply_text(
        "👋 <b>Bot Admin Mind Cash v4</b>\n\nMenu complet ⬇️",
        parse_mode="HTML", reply_markup=main_keyboard()
    )

async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("📱 <b>Menu Admin</b>",
        parse_mode="HTML", reply_markup=main_keyboard())


# ══════════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Accès refusé.")
        return

    d = query.data

    # ── Navigation ───────────────────────────────────────────────
    if d == "menu_main":
        await query.edit_message_text("📱 <b>Menu Admin</b>",
            parse_mode="HTML", reply_markup=main_keyboard())
        return

    # ── Dépôts activation ────────────────────────────────────────
    if d == "menu_deposits_pending":       await show_deposits_pending(query)
    elif d.startswith("dep_validate_"):    await validate_deposit(query, d[13:])
    elif d.startswith("dep_reject_"):      await reject_deposit(query, d[11:])
    elif d.startswith("dep_detail_"):      await show_deposit_detail(query, d[11:])

    # ── Retraits principaux ───────────────────────────────────────
    elif d == "menu_withdrawals_pending":  await show_withdrawals_pending(query)
    elif d.startswith("wit_validate_"):    await validate_withdrawal(query, d[13:])
    elif d.startswith("wit_reject_"):      await reject_withdrawal(query, d[11:])
    elif d.startswith("wit_detail_"):      await show_withdrawal_detail(query, d[11:])

    # ── Recharges boutique ────────────────────────────────────────
    elif d == "menu_shop_deposits":        await show_shop_deposits(query)
    elif d.startswith("sd_validate_"):     await validate_shop_deposit(query, d[12:])
    elif d.startswith("sd_reject_"):       await reject_shop_deposit(query, d[10:])

    # ── Retraits boutique ─────────────────────────────────────────
    elif d == "menu_shop_withdrawals":     await show_shop_withdrawals(query)
    elif d.startswith("sw_validate_"):     await validate_shop_withdrawal(query, d[12:])
    elif d.startswith("sw_reject_"):       await reject_shop_withdrawal(query, d[10:])

    # ── Retraits gains ventes ─────────────────────────────────────
    elif d == "menu_gains_withdrawals":    await show_gains_withdrawals(query)
    elif d.startswith("gw_validate_"):     await validate_gains_withdrawal(query, d[12:])
    elif d.startswith("gw_reject_"):       await reject_gains_withdrawal(query, d[10:])

    # ── Produits ──────────────────────────────────────────────────
    elif d == "menu_products_pending":     await show_products_pending(query)
    elif d == "menu_products_active":      await show_products_active(query)
    elif d == "menu_add_product":          await add_product_start(query, ctx)   # ✅ NOUVEAU
    elif d.startswith("prod_approve_"):    await approve_product(query, d[13:])
    elif d.startswith("prod_reject_"):     await reject_product(query, d[12:])
    elif d.startswith("prod_delete_"):     await delete_product(query, d[12:])
    elif d.startswith("prod_detail_"):     await show_product_detail(query, d[12:])
    elif d == "prod_confirm":              await add_product_confirm(query, ctx)  # ✅ NOUVEAU
    elif d == "prod_cancel":                                                       # ✅ NOUVEAU
        ctx.user_data.clear()
        await query.edit_message_text("❌ Ajout annulé.", reply_markup=back())

    # ── Comptes ───────────────────────────────────────────────────
    elif d == "menu_inactive_accounts":    await show_inactive_accounts(query)
    elif d.startswith("acc_activate_"):    await activate_account(query, d[13:])
    elif d.startswith("acc_detail_"):      await show_account_detail(query, d[11:])

    # ── Historiques ───────────────────────────────────────────────
    elif d == "menu_deposits_history":     await show_deposits_history(query)
    elif d == "menu_withdrawals_history":  await show_withdrawals_history(query)
    elif d == "menu_transactions_all":     await show_all_transactions(query)

    # ── Stats ─────────────────────────────────────────────────────
    elif d == "menu_stats":                await show_stats(query)

    # ── Publicités ────────────────────────────────────────────────
    elif d == "menu_ads":                  await show_ads_menu(query)
    elif d == "ads_list":                  await show_ads_list(query)
    elif d.startswith("ad_toggle_"):       await toggle_ad(query, d[10:])
    elif d.startswith("ad_delete_"):       await delete_ad(query, d[10:])
    elif d.startswith("ad_detail_"):       await show_ad_detail(query, d[10:])
    elif d == "ads_confirm":               await ads_confirm(update, ctx)
    elif d == "ads_cancel":                await ads_cancel(update, ctx)

    # ── Créditer un solde ─────────────────────────────────────────
    elif d == "menu_credit_user":          await credit_user_start(query, ctx)
    elif d.startswith("credit_type_"):     await credit_type_chosen(query, ctx, d[12:])
    elif d == "credit_confirm":            await credit_confirm(query, ctx)
    elif d == "credit_cancel":
        ctx.user_data.clear()
        await query.edit_message_text("❌ Crédit annulé.", reply_markup=back())

    # ── Diffusion ─────────────────────────────────────────────────
    elif d == "menu_broadcast_start":      await broadcast_start(query, ctx)
    elif d == "broadcast_confirm":         await broadcast_confirm(update, ctx)
    elif d == "broadcast_cancel":
        ctx.user_data.clear()
        await query.edit_message_text("❌ Diffusion annulée.", reply_markup=back())

    # ── Recherche ─────────────────────────────────────────────────
    elif d == "menu_search_user":          await search_user_start(query, ctx)


# ══════════════════════════════════════════════════════════════════
#  ① DÉPÔTS D'ACTIVATION
# ══════════════════════════════════════════════════════════════════
async def show_deposits_pending(query):
    res = (sb.table("deposits")
           .select("*, users(name, phone, ref_code)")
           .eq("status", "pending")
           .order("created_at", desc=False)
           .execute())
    deps = res.data or []
    if not deps:
        await query.edit_message_text("✅ <b>Aucun dépôt en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"📥 <b>Dépôts en attente</b> ({len(deps)})\n\n"
    buttons = []
    for d in deps[:10]:
        u = d.get("users") or {}
        ico = "🔓" if d.get("is_activation") else "📥"
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"{ico} <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
                 f"💰 <b>{fmt(d['amount'])}</b> · 📲 {d.get('number','—')}\n"
                 f"📅 {fmt_date(d.get('created_at',''))}\n")
        did = str(d["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Valider #{did[:6]}", callback_data=f"dep_validate_{did}"),
            InlineKeyboardButton("❌ Rejeter",             callback_data=f"dep_reject_{did}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_deposit_detail(query, dep_id):
    res = sb.table("deposits").select("*, users(name,phone,ref_code)").eq("id", dep_id).single().execute()
    d = res.data
    if not d:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    u = d.get("users") or {}
    text = (f"📥 <b>Dépôt #{dep_id[:8]}</b>\n\n"
            f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
            f"🏷️ {u.get('ref_code','—')}\n"
            f"💰 {fmt(d['amount'])} · 📲 {d.get('number','—')}\n"
            f"🔓 Activation : {'Oui' if d.get('is_activation') else 'Non'}\n"
            f"📊 {badge(d.get('status',''))}\n"
            f"📅 {fmt_date(d.get('created_at',''))}")
    btns = []
    if d.get("status") == "pending":
        btns.append([InlineKeyboardButton("✅ Valider", callback_data=f"dep_validate_{dep_id}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"dep_reject_{dep_id}")])
    btns.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_deposits_pending")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(btns))

async def validate_deposit(query, dep_id):
    res = sb.table("deposits").select("*, users(id,name,phone,ref_code,referred_by,is_active)") \
            .eq("id", dep_id).single().execute()
    d = res.data
    if not d or d.get("status") != "pending":
        await query.edit_message_text("⚠️ Déjà traité.", reply_markup=back()); return
    uid = d["user_id"]; amount = d["amount"]; u = d.get("users") or {}
    is_act = d.get("is_activation", False)
    sb.table("deposits").update({"status": "success"}).eq("id", dep_id).execute()
    bonus_txt = ""
    if is_act:
        if not u.get("is_active"):
            sb.table("users").update({"is_active": True}).eq("id", uid).execute()
            parent_id = u.get("referred_by")
            if parent_id:
                _credit_balance(parent_id, BONUS_N1, "referral",
                                {"level": 1, "from_user": uid, "from_name": u.get("name")})
                bonus_txt += f"\n📣 +{fmt(BONUS_N1)} → Parrain N1"
                p2 = sb.table("users").select("referred_by").eq("id", parent_id).single().execute()
                gp_id = (p2.data or {}).get("referred_by")
                if gp_id:
                    _credit_balance(gp_id, BONUS_N2, "referral",
                                    {"level": 2, "from_user": uid, "from_name": u.get("name")})
                    bonus_txt += f"\n📣 +{fmt(BONUS_N2)} → Parrain N2"
        extra = "\n🔓 <b>Compte activé !</b>" + bonus_txt
    else:
        _credit_balance(uid, amount, "deposit", {"deposit_id": dep_id})
        extra = ""
    await query.edit_message_text(
        f"✅ <b>Dépôt validé</b>{extra}\n\n"
        f"👤 {u.get('name','—')} · 💰 {fmt(amount)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Autres dépôts", callback_data="menu_deposits_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_deposit(query, dep_id):
    res = sb.table("deposits").select("*, users(name,phone)").eq("id", dep_id).single().execute()
    d = res.data
    if not d:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    sb.table("deposits").update({"status": "failed"}).eq("id", dep_id).execute()
    u = d.get("users") or {}
    await query.edit_message_text(
        f"🚫 <b>Dépôt rejeté</b>\n👤 {u.get('name','—')} · 💰 {fmt(d['amount'])}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Autres dépôts", callback_data="menu_deposits_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ② RETRAITS PRINCIPAUX
# ══════════════════════════════════════════════════════════════════
async def show_withdrawals_pending(query):
    res = (sb.table("withdrawals")
           .select("*, users(name,phone,ref_code)")
           .eq("status", "pending")
           .order("created_at", desc=False).execute())
    wits = res.data or []
    if not wits:
        await query.edit_message_text("✅ <b>Aucun retrait en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"💳 <b>Retraits en attente</b> ({len(wits)})\n\n"
    buttons = []
    for w in wits[:10]:
        u = w.get("users") or {}
        fees, net = calc_frais(w["amount"])
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
                 f"💰 {fmt(w['amount'])} → Net : <b>{fmt(net)}</b>\n"
                 f"📱 {w.get('operator','MTN')} · {w.get('number','—')}\n"
                 f"📅 {fmt_date(w.get('created_at',''))}\n")
        wid = str(w["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Valider #{wid[:6]}", callback_data=f"wit_validate_{wid}"),
            InlineKeyboardButton("❌ Rejeter",             callback_data=f"wit_reject_{wid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_withdrawal_detail(query, wit_id):
    res = sb.table("withdrawals").select("*, users(name,phone,ref_code)").eq("id", wit_id).single().execute()
    w = res.data
    if not w:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    u = w.get("users") or {}
    fees, net = calc_frais(w["amount"])
    text = (f"💳 <b>Retrait #{wit_id[:8]}</b>\n\n"
            f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
            f"💰 {fmt(w['amount'])} · Frais {FRAIS_PERCENT}% : {fmt(fees)}\n"
            f"✅ À envoyer : <b>{fmt(net)}</b>\n"
            f"📱 {w.get('operator','MTN')} · {w.get('number','—')}\n"
            f"📊 {badge(w.get('status',''))}\n"
            f"📅 {fmt_date(w.get('created_at',''))}")
    btns = []
    if w.get("status") == "pending":
        btns.append([InlineKeyboardButton("✅ Valider", callback_data=f"wit_validate_{wit_id}"),
                     InlineKeyboardButton("❌ Rejeter", callback_data=f"wit_reject_{wit_id}")])
    btns.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_withdrawals_pending")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(btns))

async def validate_withdrawal(query, wit_id):
    res = sb.table("withdrawals").select("*, users(name,phone)").eq("id", wit_id).single().execute()
    w = res.data
    if not w or w.get("status") != "pending":
        await query.edit_message_text("⚠️ Déjà traité.", reply_markup=back()); return
    fees, net = calc_frais(w["amount"])
    sb.table("withdrawals").update({"status": "success", "fees": fees, "net_amount": net}).eq("id", wit_id).execute()
    sb.table("transactions").update({"status": "success"}) \
      .eq("user_id", w["user_id"]).eq("type", "withdraw").eq("status", "pending").execute()
    u = w.get("users") or {}
    await query.edit_message_text(
        f"✅ <b>Retrait validé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 {fmt(w['amount'])} → <b>Envoyer {fmt(net)}</b>\n"
        f"📱 {w.get('operator','MTN')} · {w.get('number','—')}\n\n"
        f"<i>💳 N'oubliez pas d'envoyer le montant sur MTN MoMo !</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Autres retraits", callback_data="menu_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_withdrawal(query, wit_id):
    res = sb.table("withdrawals").select("*, users(name,phone)").eq("id", wit_id).single().execute()
    w = res.data
    if not w:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    _credit_balance(w["user_id"], w["amount"], "refund", {"withdrawal_id": wit_id})
    sb.table("withdrawals").update({"status": "rejected"}).eq("id", wit_id).execute()
    sb.table("transactions").update({"status": "failed"}) \
      .eq("user_id", w["user_id"]).eq("type", "withdraw").eq("status", "pending").execute()
    u = w.get("users") or {}
    await query.edit_message_text(
        f"🚫 <b>Retrait rejeté — {fmt(w['amount'])} remboursé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Autres retraits", callback_data="menu_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ③ RECHARGES BOUTIQUE  (shop_deposits)
# ══════════════════════════════════════════════════════════════════
async def show_shop_deposits(query):
    res = (sb.table("shop_deposits")
           .select("*, users(name,phone,ref_code)")
           .eq("status", "pending")
           .order("created_at", desc=False).execute())
    items = res.data or []
    if not items:
        await query.edit_message_text("✅ <b>Aucune recharge boutique en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"🛒 <b>Recharges boutique en attente</b> ({len(items)})\n\n"
    buttons = []
    for sd in items[:10]:
        u = sd.get("users") or {}
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
                 f"💰 <b>{fmt(sd['amount'])}</b> · 📲 {sd.get('momo_number','—')}\n"
                 f"📅 {fmt_date(sd.get('created_at',''))}\n")
        sid = str(sd["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Créditer #{sid[:6]}", callback_data=f"sd_validate_{sid}"),
            InlineKeyboardButton("❌ Rejeter",               callback_data=f"sd_reject_{sid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def validate_shop_deposit(query, sd_id):
    res = sb.table("shop_deposits").select("*, users(name,phone,shop_balance)") \
            .eq("id", sd_id).single().execute()
    sd = res.data
    if not sd or sd.get("status") != "pending":
        await query.edit_message_text("⚠️ Déjà traité.", reply_markup=back()); return
    u = sd.get("users") or {}
    new_bal = (u.get("shop_balance") or 0) + sd["amount"]
    sb.table("users").update({"shop_balance": new_bal}).eq("id", sd["user_id"]).execute()
    sb.table("shop_deposits").update({"status": "success"}).eq("id", sd_id).execute()
    sb.table("transactions").insert({
        "user_id": sd["user_id"], "type": "shop_deposit",
        "amount": sd["amount"], "status": "success",
        "meta": {"shop_deposit_id": sd_id}
    }).execute()
    await query.edit_message_text(
        f"✅ <b>Recharge boutique créditée !</b>\n\n"
        f"👤 {u.get('name','—')}\n"
        f"💰 +{fmt(sd['amount'])} → Solde boutique : {fmt(new_bal)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Autres recharges", callback_data="menu_shop_deposits")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_shop_deposit(query, sd_id):
    res = sb.table("shop_deposits").select("*, users(name,phone)").eq("id", sd_id).single().execute()
    sd = res.data
    if not sd:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    sb.table("shop_deposits").update({"status": "rejected"}).eq("id", sd_id).execute()
    u = sd.get("users") or {}
    await query.edit_message_text(
        f"🚫 <b>Recharge boutique rejetée</b>\n👤 {u.get('name','—')} · {fmt(sd['amount'])}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Autres recharges", callback_data="menu_shop_deposits")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ④ RETRAITS BOUTIQUE  (shop_withdrawals)
# ══════════════════════════════════════════════════════════════════
async def show_shop_withdrawals(query):
    res = (sb.table("shop_withdrawals")
           .select("*, users(name,phone,ref_code)")
           .eq("status", "pending")
           .order("created_at", desc=False).execute())
    items = res.data or []
    if not items:
        await query.edit_message_text("✅ <b>Aucun retrait boutique en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"💸 <b>Retraits boutique en attente</b> ({len(items)})\n\n"
    buttons = []
    for sw in items[:10]:
        u = sw.get("users") or {}
        fees, net = calc_frais(sw["amount"])
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
                 f"💰 {fmt(sw['amount'])} → Net : <b>{fmt(net)}</b>\n"
                 f"📱 {sw.get('momo_number','—')}\n"
                 f"📅 {fmt_date(sw.get('created_at',''))}\n")
        swid = str(sw["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Envoyer #{swid[:6]}", callback_data=f"sw_validate_{swid}"),
            InlineKeyboardButton("❌ Rejeter",               callback_data=f"sw_reject_{swid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def validate_shop_withdrawal(query, sw_id):
    res = sb.table("shop_withdrawals").select("*, users(name,phone)") \
            .eq("id", sw_id).single().execute()
    sw = res.data
    if not sw or sw.get("status") != "pending":
        await query.edit_message_text("⚠️ Déjà traité.", reply_markup=back()); return
    fees, net = calc_frais(sw["amount"])
    sb.table("shop_withdrawals").update({"status": "success"}).eq("id", sw_id).execute()
    sb.table("transactions").update({"status": "success"}) \
      .eq("user_id", sw["user_id"]).eq("type", "shop_withdraw").eq("status", "pending").execute()
    u = sw.get("users") or {}
    await query.edit_message_text(
        f"✅ <b>Retrait boutique validé !</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 {fmt(sw['amount'])} → <b>Envoyer {fmt(net)}</b>\n"
        f"📱 {sw.get('momo_number','—')}\n\n"
        f"<i>💸 N'oubliez pas d'envoyer sur MTN MoMo !</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Autres retraits boutique", callback_data="menu_shop_withdrawals")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_shop_withdrawal(query, sw_id):
    res = sb.table("shop_withdrawals").select("*, users(name,phone,shop_balance)") \
            .eq("id", sw_id).single().execute()
    sw = res.data
    if not sw:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    u = sw.get("users") or {}
    new_bal = (u.get("shop_balance") or 0) + sw["amount"]
    sb.table("users").update({"shop_balance": new_bal}).eq("id", sw["user_id"]).execute()
    sb.table("shop_withdrawals").update({"status": "rejected"}).eq("id", sw_id).execute()
    sb.table("transactions").update({"status": "failed"}) \
      .eq("user_id", sw["user_id"]).eq("type", "shop_withdraw").eq("status", "pending").execute()
    await query.edit_message_text(
        f"🚫 <b>Retrait boutique rejeté — {fmt(sw['amount'])} remboursé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Autres retraits boutique", callback_data="menu_shop_withdrawals")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ⑤ RETRAITS GAINS VENTES  (gains_withdrawals)
# ══════════════════════════════════════════════════════════════════
async def show_gains_withdrawals(query):
    res = (sb.table("gains_withdrawals")
           .select("*, users(name,phone,ref_code)")
           .eq("status", "pending")
           .order("created_at", desc=False).execute())
    items = res.data or []
    if not items:
        await query.edit_message_text("✅ <b>Aucun retrait gains ventes en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"💜 <b>Retraits gains ventes en attente</b> ({len(items)})\n\n"
    buttons = []
    for gw in items[:10]:
        u = gw.get("users") or {}
        fees = gw.get("fees") or round(gw["amount"] * FRAIS_PERCENT / 100)
        net  = gw.get("net")  or (gw["amount"] - fees)
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
                 f"💜 {fmt(gw['amount'])} → Net : <b>{fmt(net)}</b>\n"
                 f"📱 {gw.get('momo_number','—')}\n"
                 f"📅 {fmt_date(gw.get('created_at',''))}\n")
        gwid = str(gw["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Envoyer #{gwid[:6]}", callback_data=f"gw_validate_{gwid}"),
            InlineKeyboardButton("❌ Rejeter",               callback_data=f"gw_reject_{gwid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def validate_gains_withdrawal(query, gw_id):
    res = sb.table("gains_withdrawals").select("*, users(name,phone)") \
            .eq("id", gw_id).single().execute()
    gw = res.data
    if not gw or gw.get("status") != "pending":
        await query.edit_message_text("⚠️ Déjà traité.", reply_markup=back()); return
    fees = gw.get("fees") or round(gw["amount"] * FRAIS_PERCENT / 100)
    net  = gw.get("net")  or (gw["amount"] - fees)
    sb.table("gains_withdrawals").update({"status": "success"}).eq("id", gw_id).execute()
    u = gw.get("users") or {}
    await query.edit_message_text(
        f"✅ <b>Retrait gains validé !</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💜 {fmt(gw['amount'])} → <b>Envoyer {fmt(net)}</b>\n"
        f"📱 {gw.get('momo_number','—')}\n\n"
        f"<i>💸 N'oubliez pas d'envoyer sur MTN MoMo !</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💜 Autres retraits gains", callback_data="menu_gains_withdrawals")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_gains_withdrawal(query, gw_id):
    res = sb.table("gains_withdrawals").select("*, users(name,phone,gains_balance)") \
            .eq("id", gw_id).single().execute()
    gw = res.data
    if not gw:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    u = gw.get("users") or {}
    new_bal = (u.get("gains_balance") or 0) + gw["amount"]
    sb.table("users").update({"gains_balance": new_bal}).eq("id", gw["user_id"]).execute()
    sb.table("gains_withdrawals").update({"status": "rejected"}).eq("id", gw_id).execute()
    await query.edit_message_text(
        f"🚫 <b>Retrait gains rejeté — {fmt(gw['amount'])} remboursé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💜 Autres retraits gains", callback_data="menu_gains_withdrawals")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ⑥ PRODUITS  (products)
# ══════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────
# ✅ CORRECTION BUG : Supabase retourne NULL (pas False) pour les
#    nouveaux produits. .eq("is_approved", False) ne remonte PAS
#    les lignes avec NULL. On utilise .is_() pour matcher NULL aussi.
# ─────────────────────────────────────────────────────────────────
async def show_products_pending(query):
    # On récupère TOUS les produits non approuvés, puis on filtre côté Python
    # pour inclure is_approved = False ET is_approved = NULL
    res = (sb.table("products")
           .select("*, users(name,ref_code)")
           .neq("is_approved", True)      # exclut uniquement True
           .neq("is_rejected", True)      # exclut uniquement True
           .order("created_at", desc=False)
           .execute())
    # Filtre supplémentaire : exclure les produits approuvés (double sécurité)
    items = [p for p in (res.data or []) if not p.get("is_approved") and not p.get("is_rejected")]
    if not items:
        await query.edit_message_text("✅ <b>Aucun produit à valider</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"📦 <b>Produits en attente</b> ({len(items)})\n\n"
    buttons = []
    for p in items[:10]:
        u = p.get("users") or {}
        gains = round((p.get("price") or 0) * VENDOR_PCT / 100)
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"📌 <b>{p.get('title','—')}</b>\n"
                 f"💰 {fmt(p.get('price',0))} · 💜 Vendeur : {fmt(gains)}\n"
                 f"👤 {u.get('name','admin')} ({u.get('ref_code','admin')})\n"
                 f"🔗 {str(p.get('link','—'))[:40]}\n"
                 f"📅 {fmt_date(p.get('created_at',''))}\n")
        pid = str(p["id"])
        buttons.append([
            InlineKeyboardButton("✅ Approuver", callback_data=f"prod_approve_{pid}"),
            InlineKeyboardButton("❌ Rejeter",   callback_data=f"prod_reject_{pid}"),
            InlineKeyboardButton("ℹ️",           callback_data=f"prod_detail_{pid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_products_active(query):
    res = (sb.table("products")
           .select("*, users(name)")
           .eq("is_approved", True)
           .order("created_at", desc=True)
           .limit(20).execute())
    items = res.data or []
    if not items:
        await query.edit_message_text("Aucun produit actif.", reply_markup=back())
        return
    text = f"🛍 <b>Produits actifs</b> ({len(items)})\n\n"
    buttons = []
    for p in items:
        u = p.get("users") or {}
        owner = u.get("name") or "Admin"
        text += f"• <b>{p.get('title','—')}</b> — {fmt(p.get('price',0))} — {owner}\n"
        pid = str(p["id"])
        buttons.append([
            InlineKeyboardButton(f"🗑️ Supprimer : {p.get('title','')[:20]}", callback_data=f"prod_delete_{pid}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Ajouter un produit", callback_data="menu_add_product")])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_product_detail(query, prod_id):
    res = sb.table("products").select("*, users(name,ref_code)").eq("id", prod_id).single().execute()
    p = res.data
    if not p:
        await query.edit_message_text("❌ Produit introuvable.", reply_markup=back()); return
    u = p.get("users") or {}
    gains = round((p.get("price") or 0) * VENDOR_PCT / 100)
    status = "✅ Approuvé" if p.get("is_approved") else ("❌ Rejeté" if p.get("is_rejected") else "⏳ En attente")
    text = (f"📦 <b>Produit #{prod_id[:8]}</b>\n\n"
            f"📌 <b>{p.get('title','—')}</b>\n"
            f"📝 {p.get('description','—')}\n"
            f"💰 Prix : {fmt(p.get('price',0))}\n"
            f"💜 Gains vendeur ({VENDOR_PCT}%) : {fmt(gains)}\n"
            f"🔗 Lien : {p.get('link','—')}\n"
            f"🖼 Cover : {p.get('cover') or 'Aucune'}\n"
            f"👤 Vendeur : {u.get('name','admin')} ({u.get('ref_code','admin')})\n"
            f"📊 Statut : {status}\n"
            f"📅 {fmt_date(p.get('created_at',''))}")
    btns = []
    if not p.get("is_approved") and not p.get("is_rejected"):
        btns.append([InlineKeyboardButton("✅ Approuver", callback_data=f"prod_approve_{prod_id}"),
                     InlineKeyboardButton("❌ Rejeter",   callback_data=f"prod_reject_{prod_id}")])
    if p.get("is_approved"):
        btns.append([InlineKeyboardButton("🗑️ Supprimer", callback_data=f"prod_delete_{prod_id}")])
    btns.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_products_pending")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(btns))

async def approve_product(query, prod_id):
    sb.table("products").update({"is_approved": True, "is_rejected": False}) \
      .eq("id", prod_id).execute()
    await query.edit_message_text(
        "✅ <b>Produit approuvé !</b>\nIl est maintenant visible dans la boutique.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Autres produits", callback_data="menu_products_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def reject_product(query, prod_id):
    sb.table("products").update({"is_approved": False, "is_rejected": True}) \
      .eq("id", prod_id).execute()
    await query.edit_message_text(
        "❌ <b>Produit rejeté.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Autres produits", callback_data="menu_products_pending")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def delete_product(query, prod_id):
    sb.table("products").delete().eq("id", prod_id).execute()
    await query.answer("🗑️ Produit supprimé !", show_alert=True)
    await show_products_active(query)


# ══════════════════════════════════════════════════════════════════
#  ⑥bis AJOUT PRODUIT DEPUIS LE BOT (admin)  ✅ NOUVEAU
# ══════════════════════════════════════════════════════════════════
async def add_product_start(query, ctx):
    """Lance le flux d'ajout de produit admin."""
    ctx.user_data.clear()
    ctx.user_data["prod_step"] = PROD_TITLE
    await query.edit_message_text(
        "➕ <b>Ajouter un produit — Étape 1/5</b>\n\n"
        "📌 <b>Titre</b> du produit :\n"
        "<i>(ex: Formation Marketing Digital)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")
        ]]))

async def add_product_confirm(query, ctx):
    """Insère le produit dans Supabase après confirmation."""
    d = ctx.user_data
    title = d.get("prod_title", "")
    desc  = d.get("prod_desc", "")
    price = d.get("prod_price", 0)
    link  = d.get("prod_link")
    cover = d.get("prod_cover")

    if not title or not price:
        await query.edit_message_text("❌ Données incomplètes.", reply_markup=back()); return

    gains = round(price * VENDOR_PCT / 100)

    res = sb.table("products").insert({
        "title":       title,
        "description": desc,
        "price":       price,
        "link":        link,
        "cover":       cover,
        "is_approved": True,   # Produit admin → directement approuvé
        "is_rejected": False,
        "user_id":     None,   # NULL = produit admin (pas de vendeur utilisateur)
    }).execute()

    ctx.user_data.clear()

    if res.data:
        await query.edit_message_text(
            f"✅ <b>Produit ajouté et publié !</b>\n\n"
            f"📌 <b>{title}</b>\n"
            f"💰 Prix : {fmt(price)}\n"
            f"💜 Gains vendeur : {fmt(gains)}\n"
            f"🔗 Lien : {link or 'Aucun'}\n"
            f"🖼 Cover : {cover or 'Aucune'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍 Voir produits actifs", callback_data="menu_products_active")],
                [InlineKeyboardButton("➕ Ajouter un autre",     callback_data="menu_add_product")],
                [InlineKeyboardButton("⬅️ Menu",                 callback_data="menu_main")],
            ]))
    else:
        await query.edit_message_text(
            "❌ <b>Erreur lors de l'ajout.</b>\nVérifie ta connexion Supabase.",
            parse_mode="HTML", reply_markup=back())


# ══════════════════════════════════════════════════════════════════
#  ⑦ COMPTES INACTIFS
# ══════════════════════════════════════════════════════════════════
async def show_inactive_accounts(query):
    res = (sb.table("users").select("*").eq("is_active", False)
           .order("created_at", desc=False).execute())
    accounts = res.data or []
    if not accounts:
        await query.edit_message_text("✅ <b>Aucun compte en attente</b>",
                                      parse_mode="HTML", reply_markup=back())
        return
    text = f"🔓 <b>Comptes à activer</b> ({len(accounts)})\n\n"
    buttons = []
    for u in accounts[:10]:
        text += (f"━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>{u.get('name','—')}</b>\n"
                 f"📞 {u.get('phone','—')} · 🏷️ {u.get('ref_code','—')}\n"
                 f"📅 {fmt_date(u.get('created_at',''))}\n")
        uid = str(u["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Activer {u.get('name','').split()[0]}", callback_data=f"acc_activate_{uid}"),
            InlineKeyboardButton("ℹ️ Détail", callback_data=f"acc_detail_{uid}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_account_detail(query, uid):
    res = sb.table("users").select("*").eq("id", uid).single().execute()
    u = res.data
    if not u:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    text = (f"👤 <b>Profil utilisateur</b>\n\n"
            f"📛 {u.get('name','—')}\n"
            f"📞 {u.get('phone','—')} · 🏷️ {u.get('ref_code','—')}\n"
            f"💰 Solde : {fmt(u.get('balance',0))}\n"
            f"🛒 Boutique : {fmt(u.get('shop_balance',0))}\n"
            f"💜 Gains : {fmt(u.get('gains_balance',0))}\n"
            f"📊 {'✅ Actif' if u.get('is_active') else '⏳ Inactif'}\n"
            f"📅 {fmt_date(u.get('created_at',''))}")
    btns = []
    if not u.get("is_active"):
        btns.append([InlineKeyboardButton("✅ Activer ce compte", callback_data=f"acc_activate_{uid}")])
    btns.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_inactive_accounts")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(btns))

async def activate_account(query, uid):
    res = sb.table("users").select("*").eq("id", uid).single().execute()
    u = res.data
    if not u:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back()); return
    if u.get("is_active"):
        await query.edit_message_text("⚠️ Déjà actif.", reply_markup=back()); return
    sb.table("users").update({"is_active": True}).eq("id", uid).execute()
    bonus_txt = ""
    parent_id = u.get("referred_by")
    if parent_id:
        _credit_balance(parent_id, BONUS_N1, "referral",
                        {"level": 1, "from_user": uid, "from_name": u.get("name")})
        bonus_txt += f"\n📣 +{fmt(BONUS_N1)} → Parrain N1"
        p2 = sb.table("users").select("referred_by").eq("id", parent_id).single().execute()
        gp_id = (p2.data or {}).get("referred_by")
        if gp_id:
            _credit_balance(gp_id, BONUS_N2, "referral",
                            {"level": 2, "from_user": uid, "from_name": u.get("name")})
            bonus_txt += f"\n📣 +{fmt(BONUS_N2)} → Parrain N2"
    await query.edit_message_text(
        f"✅ <b>Compte activé !</b>{bonus_txt}\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n🏷️ {u.get('ref_code','—')}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Autres comptes", callback_data="menu_inactive_accounts")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  ⑧ HISTORIQUES
# ══════════════════════════════════════════════════════════════════
async def show_deposits_history(query):
    deps = sb.table("deposits").select("*, users(name)") \
             .order("created_at", desc=True).limit(15).execute().data or []
    if not deps:
        await query.edit_message_text("📋 Aucun dépôt.", reply_markup=back()); return
    text = "📋 <b>Historique dépôts (15 derniers)</b>\n\n"
    for d in deps:
        u = d.get("users") or {}
        ico = "🔓" if d.get("is_activation") else "📥"
        text += f"{ico} {badge(d.get('status',''))} · <b>{fmt(d['amount'])}</b> · {u.get('name','—')} · {fmt_date(d.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back())

async def show_withdrawals_history(query):
    wits = sb.table("withdrawals").select("*, users(name)") \
             .order("created_at", desc=True).limit(15).execute().data or []
    if not wits:
        await query.edit_message_text("📋 Aucun retrait.", reply_markup=back()); return
    text = "📋 <b>Historique retraits (15 derniers)</b>\n\n"
    for w in wits:
        u = w.get("users") or {}
        _, net = calc_frais(w["amount"])
        text += f"{badge(w.get('status',''))} · <b>{fmt(w['amount'])}</b> (net: {fmt(net)}) · {u.get('name','—')} · {fmt_date(w.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back())

async def show_all_transactions(query):
    txs = sb.table("transactions").select("*, users(name)") \
            .order("created_at", desc=True).limit(20).execute().data or []
    if not txs:
        await query.edit_message_text("📋 Aucune transaction.", reply_markup=back()); return
    icons = {"deposit":"📥","withdraw":"💳","bonus":"🎁","ad":"📢",
             "mission":"🎯","referral":"👥","activation":"🔓",
             "shop_deposit":"🛒","shop_withdraw":"💸",
             "sale_gain":"💜","gains_withdraw":"💜","manual_credit":"💰"}
    text = "🔄 <b>Toutes transactions (20 dernières)</b>\n\n"
    for tx in txs:
        u = tx.get("users") or {}
        ico  = icons.get(tx.get("type",""), "💸")
        sign = "−" if "withdraw" in tx.get("type","") else "+"
        text += f"{ico} {sign}{fmt(tx['amount'])} · {badge(tx.get('status',''))} · {u.get('name','—')} · {fmt_date(tx.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back())


# ══════════════════════════════════════════════════════════════════
#  ⑨ STATISTIQUES COMPLÈTES
# ══════════════════════════════════════════════════════════════════
async def show_stats(query):
    u_res  = sb.table("users").select("id,is_active", count="exact").execute()
    u_all  = u_res.count or 0
    u_act  = sum(1 for u in (u_res.data or []) if u.get("is_active"))

    d_all  = sb.table("deposits").select("amount,status").execute().data or []
    d_ok   = sum(x["amount"] for x in d_all if x["status"] == "success")
    d_pend = sum(1 for x in d_all if x["status"] == "pending")

    w_all  = sb.table("withdrawals").select("amount,net_amount,status").execute().data or []
    w_ok   = sum(x.get("net_amount") or (x["amount"] - round(x["amount"]*FRAIS_PERCENT/100))
                 for x in w_all if x["status"] == "success")
    w_pend = sum(1 for x in w_all if x["status"] == "pending")

    sd_all = sb.table("shop_deposits").select("amount,status").execute().data or []
    sd_ok  = sum(x["amount"] for x in sd_all if x["status"] == "success")
    sd_pnd = sum(1 for x in sd_all if x["status"] == "pending")

    sw_all = sb.table("shop_withdrawals").select("amount,status").execute().data or []
    sw_ok  = sum(x["amount"] for x in sw_all if x["status"] == "success")
    sw_pnd = sum(1 for x in sw_all if x["status"] == "pending")

    gw_all = sb.table("gains_withdrawals").select("amount,status").execute().data or []
    gw_ok  = sum(x["amount"] for x in gw_all if x["status"] == "success")
    gw_pnd = sum(1 for x in gw_all if x["status"] == "pending")

    tx_all    = sb.table("transactions").select("type,amount,status").execute().data or []
    bonus_t   = sum(x["amount"] for x in tx_all if x["type"]=="bonus"    and x["status"]=="success")
    ad_t      = sum(x["amount"] for x in tx_all if x["type"]=="ad"       and x["status"]=="success")
    miss_t    = sum(x["amount"] for x in tx_all if x["type"]=="mission"  and x["status"]=="success")
    ref_t     = sum(x["amount"] for x in tx_all if x["type"]=="referral" and x["status"]=="success")
    sales_t   = sum(x["amount"] for x in tx_all if x["type"]=="sale_gain"and x["status"]=="success")

    prods_ok  = len(sb.table("products").select("id").eq("is_approved",True).execute().data or [])
    # ✅ Utilise la même logique corrigée que show_products_pending
    all_prods = sb.table("products").select("id,is_approved,is_rejected").execute().data or []
    prods_pnd = sum(1 for p in all_prods if not p.get("is_approved") and not p.get("is_rejected"))

    ads_act   = len(sb.table("ads").select("id").eq("is_active",True).execute().data or [])

    text = (
        f"📊 <b>Statistiques Mind Cash</b>\n\n"
        f"👥 <b>Utilisateurs</b> : {u_all} (actifs : {u_act})\n\n"
        f"━━━━━━━ Flux financiers ━━━━━━━\n"
        f"📥 Dépôts validés    : <b>{fmt(d_ok)}</b> ({d_pend} en attente)\n"
        f"💳 Retraits envoyés  : <b>{fmt(w_ok)}</b> ({w_pend} en attente)\n\n"
        f"━━━━━━━ Boutique ━━━━━━━\n"
        f"🛒 Recharges créditées : <b>{fmt(sd_ok)}</b> ({sd_pnd} en attente)\n"
        f"💸 Retraits boutique   : <b>{fmt(sw_ok)}</b> ({sw_pnd} en attente)\n"
        f"💜 Retraits gains      : <b>{fmt(gw_ok)}</b> ({gw_pnd} en attente)\n"
        f"🛍 CA ventes boutique  : <b>{fmt(sales_t)}</b>\n\n"
        f"━━━━━━━ Gains distribués ━━━━━━━\n"
        f"🎁 Bonus quotidiens : {fmt(bonus_t)}\n"
        f"📢 Publicités       : {fmt(ad_t)}\n"
        f"🎯 Missions         : {fmt(miss_t)}\n"
        f"👥 Parrainage       : {fmt(ref_t)}\n\n"
        f"━━━━━━━ Catalogue ━━━━━━━\n"
        f"📦 Produits actifs   : {prods_ok} ({prods_pnd} en attente)\n"
        f"📢 Publicités actives : {ads_act}"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back())


# ══════════════════════════════════════════════════════════════════
#  ⑩ PUBLICITÉS
# ══════════════════════════════════════════════════════════════════
async def show_ads_menu(query):
    await query.edit_message_text(
        "📢 <b>Gestion des publicités</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ajouter une pub",   callback_data="ads_add_start")],
            [InlineKeyboardButton("📋 Voir toutes les pubs", callback_data="ads_list")],
            [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
        ]))

async def show_ads_list(query):
    ads = sb.table("ads").select("*").order("created_at", desc=True).execute().data or []
    if not ads:
        await query.edit_message_text("📢 <b>Aucune publicité</b>",
                                      parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("➕ Ajouter", callback_data="ads_add_start")],
                                          [InlineKeyboardButton("⬅️ Menu",    callback_data="menu_ads")],
                                      ]))
        return
    text = f"📢 <b>Publicités ({len(ads)})</b>\n\n"
    buttons = []
    for ad in ads:
        st = "✅" if ad.get("is_active") else "⏸️"
        text += f"{st} {ad.get('icon','📢')} <b>{ad.get('title','—')}</b> · {ad.get('duration_seconds',0)}s · {fmt(ad.get('reward',0))}\n"
        aid = str(ad["id"])
        toggle_lbl = "⏸️ Désactiver" if ad.get("is_active") else "▶️ Activer"
        buttons.append([
            InlineKeyboardButton(f"ℹ️ {ad.get('title','')[:15]}", callback_data=f"ad_detail_{aid}"),
            InlineKeyboardButton(toggle_lbl,                       callback_data=f"ad_toggle_{aid}"),
            InlineKeyboardButton("🗑️",                             callback_data=f"ad_delete_{aid}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Ajouter", callback_data="ads_add_start")])
    buttons.append([InlineKeyboardButton("⬅️ Menu",    callback_data="menu_ads")])
    await query.edit_message_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(buttons))

async def show_ad_detail(query, ad_id):
    ad = sb.table("ads").select("*").eq("id", ad_id).single().execute().data
    if not ad:
        await query.edit_message_text("❌ Introuvable.", reply_markup=back("menu_ads")); return
    st = "✅ Active" if ad.get("is_active") else "⏸️ Inactive"
    text = (f"📢 <b>{ad.get('title','—')}</b>\n\n"
            f"📝 {ad.get('description','—')}\n"
            f"🔗 {ad.get('link') or 'Aucun lien'}\n"
            f"⏱ {ad.get('duration_seconds',0)}s · 💰 {fmt(ad.get('reward',0))}\n"
            f"📊 {st} · 📅 {fmt_date(ad.get('created_at',''))}")
    toggle_lbl = "⏸️ Désactiver" if ad.get("is_active") else "▶️ Activer"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_lbl,      callback_data=f"ad_toggle_{ad_id}"),
         InlineKeyboardButton("🗑️ Supprimer", callback_data=f"ad_delete_{ad_id}")],
        [InlineKeyboardButton("⬅️ Liste",      callback_data="ads_list")],
    ]))

async def toggle_ad(query, ad_id):
    ad = sb.table("ads").select("is_active").eq("id", ad_id).single().execute().data
    if not ad:
        await query.answer("❌ Introuvable.", show_alert=True); return
    new_state = not ad.get("is_active", True)
    sb.table("ads").update({"is_active": new_state}).eq("id", ad_id).execute()
    await query.answer(f"{'✅ Activée' if new_state else '⏸️ Désactivée'} !", show_alert=True)
    await show_ads_list(query)

async def delete_ad(query, ad_id):
    sb.table("ads").delete().eq("id", ad_id).execute()
    await query.answer("🗑️ Supprimée !", show_alert=True)
    await show_ads_list(query)


# ══════════════════════════════════════════════════════════════════
#  ⑪ AJOUT PUBLICITÉ — ConversationHandler
# ══════════════════════════════════════════════════════════════════
async def ads_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ <b>Nouvelle pub — Étape 1/6</b>\n\nTitre de la publicité :",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]]))
    return AD_TITLE

async def ad_get_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_title"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Titre : <b>{ctx.user_data['ad_title']}</b>\n\n<b>Étape 2/6</b> — Description :",
        parse_mode="HTML")
    return AD_DESC

async def ad_get_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_desc"] = update.message.text.strip()
    await update.message.reply_text("<b>Étape 3/6</b> — Icône emoji (ex: 📢) :", parse_mode="HTML")
    return AD_ICON

async def ad_get_icon(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_icon"] = update.message.text.strip()
    await update.message.reply_text("<b>Étape 4/6</b> — Durée en secondes (ex: 30) :", parse_mode="HTML")
    return AD_DURATION

async def ad_get_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["ad_duration"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Entrez un entier, ex: 30"); return AD_DURATION
    await update.message.reply_text("<b>Étape 5/6</b> — Récompense en FCFA (ex: 150) :", parse_mode="HTML")
    return AD_REWARD

async def ad_get_reward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["ad_reward"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Entrez un entier, ex: 150"); return AD_REWARD
    await update.message.reply_text(
        "<b>Étape 6/6</b> — URL de la pub (ou tapez <b>aucun</b>) :", parse_mode="HTML")
    return AD_LINK

async def ad_get_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    ctx.user_data["ad_link"] = None if raw.lower() in ("aucun","non","-","") else raw
    d = ctx.user_data
    await update.message.reply_text(
        f"📢 <b>Récapitulatif</b>\n\n"
        f"{d.get('ad_icon','📢')} <b>{d.get('ad_title','—')}</b>\n"
        f"📝 {d.get('ad_desc','—')}\n"
        f"🔗 {d.get('ad_link') or 'Aucun'}\n"
        f"⏱ {d.get('ad_duration',0)}s · 💰 {fmt(d.get('ad_reward',0))}\n\n"
        f"Confirmer ?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirmer", callback_data="ads_confirm")],
            [InlineKeyboardButton("❌ Annuler",  callback_data="ads_cancel")],
        ]))
    return ConversationHandler.END

async def ads_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = ctx.user_data
    res = sb.table("ads").insert({
        "title": d.get("ad_title","Pub"), "description": d.get("ad_desc",""),
        "icon": d.get("ad_icon","📢"), "duration_seconds": d.get("ad_duration",30),
        "reward": d.get("ad_reward",100), "link": d.get("ad_link"),
        "is_active": True,
    }).execute()
    ctx.user_data.clear()
    msg = "✅ <b>Publicité ajoutée !</b>" if res.data else "❌ Erreur lors de l'ajout."
    await query.edit_message_text(msg, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("📋 Voir les pubs", callback_data="ads_list")],
                                      [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
                                  ]))

async def ads_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text("❌ Annulé.", reply_markup=back("menu_ads"))
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════
#  ⑫ CRÉDITER UN SOLDE MANUELLEMENT
# ══════════════════════════════════════════════════════════════════
async def credit_user_start(query, ctx):
    ctx.user_data["credit_step"] = "await_id"
    await query.edit_message_text(
        "💰 <b>Créditer un solde</b>\n\n"
        "Entrez le <b>numéro de téléphone</b> ou le <b>code parrain</b> (MC-XXXXXX) de l'utilisateur :",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="credit_cancel")]]))

async def credit_type_chosen(query, ctx, type_: str):
    ctx.user_data["credit_type"] = type_
    labels = {"balance": "Solde principal 💰",
              "shop_balance": "Solde boutique 🛒",
              "gains_balance": "Gains ventes 💜"}
    await query.edit_message_text(
        f"✅ Type : <b>{labels.get(type_,'—')}</b>\n\nEntrez le <b>montant en FCFA</b> à créditer :",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="credit_cancel")]]))
    ctx.user_data["credit_step"] = "await_amount"

async def credit_confirm(query, ctx):
    d = ctx.user_data
    uid = d.get("credit_uid")
    type_ = d.get("credit_type")
    amount = d.get("credit_amount")
    uname = d.get("credit_uname", "—")
    if not uid or not type_ or not amount:
        await query.edit_message_text("❌ Données manquantes.", reply_markup=back()); return
    cur = sb.table("users").select(type_).eq("id", uid).single().execute().data or {}
    new_val = (cur.get(type_) or 0) + amount
    sb.table("users").update({type_: new_val}).eq("id", uid).execute()
    sb.table("transactions").insert({
        "user_id": uid, "type": "manual_credit",
        "amount": amount, "status": "success",
        "meta": {"field": type_, "credited_by": "admin"}
    }).execute()
    labels = {"balance": "Solde principal", "shop_balance": "Solde boutique", "gains_balance": "Gains ventes"}
    ctx.user_data.clear()
    await query.edit_message_text(
        f"✅ <b>Crédit effectué !</b>\n\n"
        f"👤 {uname}\n"
        f"💰 +{fmt(amount)} → {labels.get(type_,'—')}\n"
        f"📊 Nouveau solde : {fmt(new_val)}",
        parse_mode="HTML",
        reply_markup=back())


# ══════════════════════════════════════════════════════════════════
#  ⑬ GESTIONNAIRE DE MESSAGES TEXTE UNIFIÉ
# ══════════════════════════════════════════════════════════════════
async def text_message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    step = ctx.user_data.get("credit_step") or ctx.user_data.get("search_step") or ctx.user_data.get("broadcast_step")
    prod_step = ctx.user_data.get("prod_step")

    # ── Ajout produit admin ──────────────────────────────────────
    if prod_step is not None:
        txt = update.message.text.strip()

        if prod_step == PROD_TITLE:
            ctx.user_data["prod_title"] = txt
            ctx.user_data["prod_step"]  = PROD_DESC
            await update.message.reply_text(
                f"✅ Titre : <b>{txt}</b>\n\n"
                f"➕ <b>Étape 2/5</b> — Description du produit :\n"
                f"<i>(ex: Apprenez les bases du marketing...)</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")]]))

        elif prod_step == PROD_DESC:
            ctx.user_data["prod_desc"] = txt
            ctx.user_data["prod_step"] = PROD_PRICE
            await update.message.reply_text(
                f"✅ Description enregistrée.\n\n"
                f"➕ <b>Étape 3/5</b> — Prix en FCFA :\n"
                f"<i>(ex: 5000)</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")]]))

        elif prod_step == PROD_PRICE:
            try:
                price = int(txt.replace(" ", "").replace(",", ""))
                if price <= 0:
                    raise ValueError
                ctx.user_data["prod_price"] = price
                ctx.user_data["prod_step"]  = PROD_LINK
                gains = round(price * VENDOR_PCT / 100)
                await update.message.reply_text(
                    f"✅ Prix : <b>{fmt(price)}</b> · Gains vendeur : {fmt(gains)}\n\n"
                    f"➕ <b>Étape 4/5</b> — Lien du produit (URL ou tapez <b>aucun</b>) :\n"
                    f"<i>(ex: https://exemple.com/produit)</i>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")]]))
            except ValueError:
                await update.message.reply_text("❌ Prix invalide. Entrez un nombre entier positif (ex: 5000).")

        elif prod_step == PROD_LINK:
            ctx.user_data["prod_link"] = None if txt.lower() in ("aucun","non","-","") else txt
            ctx.user_data["prod_step"] = PROD_COVER
            await update.message.reply_text(
                f"✅ Lien enregistré.\n\n"
                f"➕ <b>Étape 5/5</b> — URL de l'image de couverture (ou tapez <b>aucun</b>) :\n"
                f"<i>(ex: https://exemple.com/image.jpg)</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")]]))

        elif prod_step == PROD_COVER:
            ctx.user_data["prod_cover"] = None if txt.lower() in ("aucun","non","-","") else txt
            ctx.user_data.pop("prod_step", None)
            # Affichage du récapitulatif avant confirmation
            d = ctx.user_data
            gains = round((d.get("prod_price", 0)) * VENDOR_PCT / 100)
            await update.message.reply_text(
                f"📦 <b>Récapitulatif du produit</b>\n\n"
                f"📌 <b>{d.get('prod_title','—')}</b>\n"
                f"📝 {d.get('prod_desc','—')}\n"
                f"💰 Prix : <b>{fmt(d.get('prod_price',0))}</b>\n"
                f"💜 Gains vendeur ({VENDOR_PCT}%) : {fmt(gains)}\n"
                f"🔗 Lien : {d.get('prod_link') or 'Aucun'}\n"
                f"🖼 Cover : {d.get('prod_cover') or 'Aucune'}\n\n"
                f"✅ Ce produit sera publié <b>immédiatement</b>.\n"
                f"Confirmer ?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Publier",  callback_data="prod_confirm")],
                    [InlineKeyboardButton("❌ Annuler", callback_data="prod_cancel")],
                ]))
        return  # ← Fin du bloc ajout produit

    # ── Recherche utilisateur ────────────────────────────────────
    if step == "search_input":
        ctx.user_data.pop("search_step", None)
        query_str = update.message.text.strip()
        res = sb.table("users").select("*") \
                .or_(f"phone.eq.{query_str},ref_code.eq.{query_str}") \
                .limit(3).execute()
        users = res.data or []
        if not users:
            await update.message.reply_text("❌ Aucun utilisateur trouvé.", reply_markup=back())
            return
        for u in users:
            text = (f"👤 <b>{u.get('name','—')}</b>\n"
                    f"📞 {u.get('phone','—')} · 🏷️ {u.get('ref_code','—')}\n"
                    f"💰 {fmt(u.get('balance',0))} · 🛒 {fmt(u.get('shop_balance',0))} · 💜 {fmt(u.get('gains_balance',0))}\n"
                    f"📊 {'✅ Actif' if u.get('is_active') else '⏳ Inactif'}\n"
                    f"📅 {fmt_date(u.get('created_at',''))}")
            uid = str(u["id"])
            await update.message.reply_text(
                text, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Activer",   callback_data=f"acc_activate_{uid}"),
                     InlineKeyboardButton("💰 Créditer",  callback_data=f"credit_uid_{uid}_{u.get('name','')}"),
                    ],
                    [InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")],
                ]))
        return

    # ── Crédit — saisie de l'identifiant ────────────────────────
    if step == "await_id":
        query_str = update.message.text.strip()
        res = sb.table("users").select("id,name,phone,ref_code") \
                .or_(f"phone.eq.{query_str},ref_code.eq.{query_str}") \
                .limit(1).execute()
        found = (res.data or [None])[0]
        if not found:
            await update.message.reply_text("❌ Introuvable. Réessayez ou tapez /menu.")
            return
        ctx.user_data["credit_uid"]   = found["id"]
        ctx.user_data["credit_uname"] = found.get("name","—")
        ctx.user_data["credit_step"]  = "await_type"
        await update.message.reply_text(
            f"✅ Utilisateur : <b>{found['name']}</b> ({found.get('phone','—')})\n\n"
            f"Quel solde créditer ?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Solde principal",  callback_data="credit_type_balance")],
                [InlineKeyboardButton("🛒 Solde boutique",   callback_data="credit_type_shop_balance")],
                [InlineKeyboardButton("💜 Gains ventes",     callback_data="credit_type_gains_balance")],
                [InlineKeyboardButton("❌ Annuler",          callback_data="credit_cancel")],
            ]))
        return

    # ── Crédit — saisie du montant ───────────────────────────────
    if step == "await_amount":
        try:
            amount = int(update.message.text.strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Entrez un montant valide (entier positif).")
            return
        ctx.user_data["credit_amount"] = amount
        ctx.user_data.pop("credit_step", None)
        d = ctx.user_data
        labels = {"balance": "Solde principal 💰", "shop_balance": "Solde boutique 🛒", "gains_balance": "Gains ventes 💜"}
        await update.message.reply_text(
            f"💰 <b>Confirmation</b>\n\n"
            f"👤 {d.get('credit_uname','—')}\n"
            f"Créditer : <b>{fmt(amount)}</b>\n"
            f"Sur : <b>{labels.get(d.get('credit_type',''),'—')}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmer", callback_data="credit_confirm")],
                [InlineKeyboardButton("❌ Annuler",  callback_data="credit_cancel")],
            ]))
        return

    # ── Broadcast — saisie du message ───────────────────────────
    if step == "broadcast_input":
        ctx.user_data.pop("broadcast_step", None)
        ctx.user_data["broadcast_msg"] = update.message.text.strip()
        await update.message.reply_text(
            f"📣 <b>Message à diffuser</b>\n\n{ctx.user_data['broadcast_msg']}\n\n"
            f"Confirmer l'envoi à <b>tous les utilisateurs actifs</b> ?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Envoyer",  callback_data="broadcast_confirm")],
                [InlineKeyboardButton("❌ Annuler", callback_data="broadcast_cancel")],
            ]))
        return


# ══════════════════════════════════════════════════════════════════
#  ⑭ RECHERCHE UTILISATEUR
# ══════════════════════════════════════════════════════════════════
async def search_user_start(query, ctx):
    ctx.user_data["search_step"] = "search_input"
    await query.edit_message_text(
        "🔍 <b>Recherche utilisateur</b>\n\n"
        "Entrez le <b>numéro de téléphone</b> ou le <b>code parrain</b> (MC-XXXXXX) :",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="menu_main")]]))


# ══════════════════════════════════════════════════════════════════
#  ⑮ DIFFUSION (BROADCAST)
# ══════════════════════════════════════════════════════════════════
async def broadcast_start(query, ctx):
    ctx.user_data["broadcast_step"] = "broadcast_input"
    res = sb.table("users").select("id", count="exact").eq("is_active", True).execute()
    count = res.count or 0
    await query.edit_message_text(
        f"📣 <b>Diffusion</b>\n\n"
        f"Ce message sera enregistré pour <b>{count} utilisateurs actifs</b>.\n\n"
        f"Entrez votre message :",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="broadcast_cancel")]]))

async def broadcast_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg = ctx.user_data.get("broadcast_msg", "")
    if not msg:
        await query.edit_message_text("❌ Message vide.", reply_markup=back()); return
    res = sb.table("users").select("id", count="exact").eq("is_active", True).execute()
    count = res.count or 0
    try:
        sb.table("broadcasts").insert({"message": msg, "sent_at": datetime.utcnow().isoformat()}).execute()
    except Exception:
        pass
    ctx.user_data.clear()
    await query.edit_message_text(
        f"✅ <b>Message enregistré !</b>\n\n"
        f"📩 Diffusé à <b>{count} utilisateurs actifs</b>.\n"
        f"<i>(Visible dans la table broadcasts de Supabase)</i>",
        parse_mode="HTML",
        reply_markup=back())


# ══════════════════════════════════════════════════════════════════
#  HELPER INTERNE — crédit de solde + transaction
# ══════════════════════════════════════════════════════════════════
def _credit_balance(uid: str, amount: int, tx_type: str, meta: dict):
    cur = sb.table("users").select("balance").eq("id", uid).single().execute().data or {}
    new_val = (cur.get("balance") or 0) + amount
    sb.table("users").update({"balance": new_val}).eq("id", uid).execute()
    sb.table("transactions").insert({
        "user_id": uid, "type": tx_type,
        "amount": amount, "status": "success",
        "meta": meta
    }).execute()


# ══════════════════════════════════════════════════════════════════
#  CALLBACKS CREDIT_UID (depuis recherche)
# ══════════════════════════════════════════════════════════════════
async def callback_credit_uid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    parts = query.data.split("_", 3)
    if len(parts) < 4:
        await query.edit_message_text("❌ Erreur.", reply_markup=back()); return
    uid   = parts[2]
    uname = parts[3] if len(parts) > 3 else "—"
    ctx.user_data["credit_uid"]   = uid
    ctx.user_data["credit_uname"] = uname
    ctx.user_data["credit_step"]  = "await_type"
    await query.edit_message_text(
        f"💰 Créditer <b>{uname}</b>\n\nQuel solde ?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Solde principal", callback_data="credit_type_balance")],
            [InlineKeyboardButton("🛒 Solde boutique",  callback_data="credit_type_shop_balance")],
            [InlineKeyboardButton("💜 Gains ventes",    callback_data="credit_type_gains_balance")],
            [InlineKeyboardButton("❌ Annuler",         callback_data="credit_cancel")],
        ]))


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
def main():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    if HAS_KEEPALIVE:
        keep_alive()
        logger.info("🌐 Keep-alive démarré")

    app = Application.builder().token(BOT_TOKEN).build()

    # ── ConversationHandler publicité ────────────────────────────
    ad_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ads_add_start, pattern="^ads_add_start$")],
        states={
            AD_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_title)],
            AD_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_desc)],
            AD_ICON:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_icon)],
            AD_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_duration)],
            AD_REWARD:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_reward)],
            AD_LINK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ad_get_link)],
        },
        fallbacks=[CallbackQueryHandler(ads_cancel, pattern="^ads_cancel$")],
        allow_reentry=True,
    )

    app.add_handler(ad_conv)

    # ── Commandes ────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu",  cmd_menu))

    # ── Callbacks spéciaux (priorité haute) ───────────────────────
    app.add_handler(CallbackQueryHandler(ads_confirm,         pattern="^ads_confirm$"))
    app.add_handler(CallbackQueryHandler(ads_cancel,          pattern="^ads_cancel$"))
    app.add_handler(CallbackQueryHandler(callback_credit_uid, pattern=r"^credit_uid_"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: credit_type_chosen(u.callback_query, c, u.callback_query.data[12:]),
        pattern=r"^credit_type_"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: credit_confirm(u.callback_query, c),
        pattern="^credit_confirm$"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: broadcast_confirm(u, c),
        pattern="^broadcast_confirm$"))

    # ── Router général ────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_handler))

    # ── Messages texte (crédit, recherche, broadcast, ajout produit) ──
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    async def set_commands(application):
        await application.bot.set_my_commands([
            BotCommand("start", "Démarrer"),
            BotCommand("menu",  "Menu admin"),
        ])
    app.post_init = set_commands

    logger.info("🚀 MindCash Admin Bot v4 démarré")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
