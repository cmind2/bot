import asyncio
import logging
import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ══════════════════════════════════════════════════════════════════
#  ⚙️  KEEP ALIVE — Import du serveur Flask
# ══════════════════════════════════════════════════════════════════
from keep_alive import keep_alive

# ══════════════════════════════════════════════════════════════════
#  ⚙️  CONFIGURATION — Variables d'environnement
# ══════════════════════════════════════════════════════════════════
load_dotenv()

BOT_TOKEN     = os.getenv("BOT_TOKEN")
SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY")
ADMIN_CHAT_ID = list(map(int, filter(None, os.getenv("ADMIN_CHAT_ID", "").split(","))))
FRAIS_PERCENT = int(os.getenv("FRAIS_PERCENT", "5"))

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Variables d'environnement manquantes. Vérifiez votre fichier .env")

# ── États du ConversationHandler (ajout pub) ──────────────────────
AD_TITLE, AD_DESC, AD_ICON, AD_DURATION, AD_REWARD, AD_LINK = range(6)

# ══════════════════════════════════════════════════════════════════
#  INIT
# ══════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_CHAT_ID


def fmt(amount) -> str:
    try:
        return f"{int(amount):,} FCFA".replace(",", " ")
    except Exception:
        return f"{amount} FCFA"


def fmt_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


def badge_status(status: str) -> str:
    return {
        "pending":  "⏳ En attente",
        "success":  "✅ Validé",
        "failed":   "❌ Échoué",
        "rejected": "🚫 Rejeté",
    }.get(status, status)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Dépôts en attente",   callback_data="menu_deposits_pending"),
            InlineKeyboardButton("💳 Retraits en attente", callback_data="menu_withdrawals_pending"),
        ],
        [
            InlineKeyboardButton("🔓 Comptes à activer",   callback_data="menu_inactive_accounts"),
        ],
        [
            InlineKeyboardButton("📋 Historique dépôts",   callback_data="menu_deposits_history"),
            InlineKeyboardButton("📋 Historique retraits", callback_data="menu_withdrawals_history"),
        ],
        [
            InlineKeyboardButton("🔄 Toutes transactions", callback_data="menu_transactions_all"),
            InlineKeyboardButton("📊 Statistiques",        callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton("📢 Gérer les publicités", callback_data="menu_ads"),
        ],
    ])


def back_button(dest="menu_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu principal", callback_data=dest)]])


# ══════════════════════════════════════════════════════════════════
#  COMMANDES
# ══════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Accès refusé.")
        return
    await update.message.reply_text(
        "👋 <b>Bot Admin Mind Cash</b>\n\nTapez /menu pour afficher le menu.",
        parse_mode="HTML", reply_markup=main_keyboard()
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Accès refusé.")
        return
    await update.message.reply_text(
        "📱 <b>Menu Admin — Mind Cash</b>",
        parse_mode="HTML", reply_markup=main_keyboard()
    )


# ══════════════════════════════════════════════════════════════════
#  CALLBACK ROUTER
# ══════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Accès refusé.")
        return

    data = query.data

    if data == "menu_main":
        await query.edit_message_text("📱 <b>Menu Admin — Mind Cash</b>",
                                      parse_mode="HTML", reply_markup=main_keyboard())

    # ── Dépôts ───────────────────────────────────────────────────
    elif data == "menu_deposits_pending":
        await show_deposits_pending(query)
    elif data.startswith("dep_validate_"):
        await validate_deposit(query, data.replace("dep_validate_", ""))
    elif data.startswith("dep_reject_"):
        await reject_deposit(query, data.replace("dep_reject_", ""))
    elif data.startswith("dep_detail_"):
        await show_deposit_detail(query, data.replace("dep_detail_", ""))

    # ── Retraits ─────────────────────────────────────────────────
    elif data == "menu_withdrawals_pending":
        await show_withdrawals_pending(query)
    elif data.startswith("wit_validate_"):
        await validate_withdrawal(query, data.replace("wit_validate_", ""))
    elif data.startswith("wit_reject_"):
        await reject_withdrawal(query, data.replace("wit_reject_", ""))
    elif data.startswith("wit_detail_"):
        await show_withdrawal_detail(query, data.replace("wit_detail_", ""))

    # ── Comptes ──────────────────────────────────────────────────
    elif data == "menu_inactive_accounts":
        await show_inactive_accounts(query)
    elif data.startswith("acc_activate_"):
        await activate_account(query, data.replace("acc_activate_", ""))
    elif data.startswith("acc_detail_"):
        await show_account_detail(query, data.replace("acc_detail_", ""))

    # ── Historiques ──────────────────────────────────────────────
    elif data == "menu_deposits_history":
        await show_deposits_history(query)
    elif data == "menu_withdrawals_history":
        await show_withdrawals_history(query)
    elif data == "menu_transactions_all":
        await show_all_transactions(query)

    # ── Stats ────────────────────────────────────────────────────
    elif data == "menu_stats":
        await show_stats(query)

    # ── Pubs ─────────────────────────────────────────────────────
    elif data == "menu_ads":
        await show_ads_menu(query)
    elif data == "ads_list":
        await show_ads_list(query)
    elif data.startswith("ad_toggle_"):
        await toggle_ad(query, data.replace("ad_toggle_", ""))
    elif data.startswith("ad_delete_"):
        await delete_ad(query, data.replace("ad_delete_", ""))
    elif data.startswith("ad_detail_"):
        await show_ad_detail(query, data.replace("ad_detail_", ""))
    elif data == "ads_confirm":
        await ads_confirm(update, ctx)
    elif data == "ads_cancel":
        await ads_cancel(update, ctx)


# ══════════════════════════════════════════════════════════════════
#  ✅ DÉPÔTS EN ATTENTE
# ══════════════════════════════════════════════════════════════════
async def show_deposits_pending(query):
    res = (
        sb.table("deposits")
        .select("*, users(name, phone, ref_code)")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    deps = res.data or []

    if not deps:
        await query.edit_message_text("✅ <b>Aucun dépôt en attente</b>",
                                      parse_mode="HTML", reply_markup=back_button())
        return

    text = f"📥 <b>Dépôts en attente</b> ({len(deps)})\n\n"
    buttons = []

    for d in deps[:10]:
        u = d.get("users") or {}
        act = "🔓 Activation" if d.get("is_activation") else "📥 Dépôt"
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{act}\n"
            f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
            f"💰 <b>{fmt(d.get('amount',0))}</b> · {d.get('operator','—')}\n"
            f"📲 {d.get('number','—')} · 📅 {fmt_date(d.get('created_at',''))}\n"
        )
        did = str(d["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Valider #{did[:6]}", callback_data=f"dep_validate_{did}"),
            InlineKeyboardButton("❌ Rejeter",             callback_data=f"dep_reject_{did}"),
        ])

    buttons.append([InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def show_deposit_detail(query, dep_id: str):
    res = sb.table("deposits").select("*, users(name, phone, ref_code)").eq("id", dep_id).single().execute()
    d = res.data
    if not d:
        await query.edit_message_text("❌ Dépôt introuvable.", reply_markup=back_button())
        return
    u = d.get("users") or {}
    text = (
        f"📥 <b>Détail dépôt</b>\n\n"
        f"🆔 <code>{d['id']}</code>\n"
        f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
        f"🏷️ Ref : {u.get('ref_code','—')}\n"
        f"💰 Montant : <b>{fmt(d['amount'])}</b>\n"
        f"📱 {d.get('operator','—')} · {d.get('number','—')}\n"
        f"🔓 Activation : {'Oui' if d.get('is_activation') else 'Non'}\n"
        f"📊 {badge_status(d.get('status',''))}\n"
        f"📅 {fmt_date(d.get('created_at',''))}\n"
    )
    buttons = []
    if d.get("status") == "pending":
        buttons.append([
            InlineKeyboardButton("✅ Valider", callback_data=f"dep_validate_{dep_id}"),
            InlineKeyboardButton("❌ Rejeter", callback_data=f"dep_reject_{dep_id}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_deposits_pending")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def validate_deposit(query, dep_id: str):
    res = (
        sb.table("deposits")
        .select("*, users(id, name, phone, ref_code, referred_by, is_active)")
        .eq("id", dep_id)
        .single()
        .execute()
    )
    d = res.data
    if not d or d.get("status") != "pending":
        await query.edit_message_text("⚠️ Dépôt déjà traité ou introuvable.", reply_markup=back_button())
        return

    uid    = d["user_id"]
    amount = d["amount"]
    u      = d.get("users") or {}
    is_act = d.get("is_activation", False)

    sb.table("deposits").update({"status": "success"}).eq("id", dep_id).execute()

    if is_act:
        sb.table("transactions").update({"status": "success", "type": "activation"}) \
          .eq("user_id", uid).eq("type", "deposit").eq("status", "pending").execute()

        if not u.get("is_active"):
            sb.table("users").update({"is_active": True}).eq("id", uid).execute()

            parent_id = u.get("referred_by")
            if parent_id:
                sb.rpc("increment_balance", {"uid": parent_id, "amount": 2000}).execute()
                sb.table("transactions").insert({
                    "user_id": parent_id,
                    "type":    "referral",
                    "amount":  2000,
                    "status":  "success",
                    "meta":    {"level": 1, "from_user": uid, "from_name": u.get("name")}
                }).execute()

                p2 = sb.table("users").select("referred_by").eq("id", parent_id).single().execute()
                gp_id = (p2.data or {}).get("referred_by")
                if gp_id:
                    sb.rpc("increment_balance", {"uid": gp_id, "amount": 700}).execute()
                    sb.table("transactions").insert({
                        "user_id": gp_id,
                        "type":    "referral",
                        "amount":  700,
                        "status":  "success",
                        "meta":    {"level": 2, "from_user": uid, "from_name": u.get("name")}
                    }).execute()

        acti_txt = "\n🔓 <b>Compte activé !</b> Bonus parrainage crédités."
        note_txt = (
            "\n\n<i>ℹ️ Le montant du dépôt d'activation n'est pas ajouté "
            "au solde disponible (c'est un frais d'entrée unique).</i>"
        )
    else:
        sb.table("transactions").update({"status": "success"}) \
          .eq("user_id", uid).eq("type", "deposit").eq("status", "pending").execute()
        sb.rpc("increment_balance", {"uid": uid, "amount": amount}).execute()
        acti_txt = ""
        note_txt = ""

    text = (
        f"✅ <b>Dépôt validé</b>{acti_txt}\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 Montant : <b>{fmt(amount)}</b>\n"
        f"📲 {d.get('number','—')}"
        f"{note_txt}"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Autres dépôts", callback_data="menu_deposits_pending")],
        [InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")],
    ]))


async def reject_deposit(query, dep_id: str):
    res = sb.table("deposits").select("*, users(name, phone)").eq("id", dep_id).single().execute()
    d = res.data
    if not d:
        await query.edit_message_text("❌ Dépôt introuvable.", reply_markup=back_button())
        return

    sb.table("deposits").update({"status": "failed"}).eq("id", dep_id).execute()
    sb.table("transactions").update({"status": "failed"}) \
      .eq("user_id", d["user_id"]).eq("type", "deposit").eq("status", "pending").execute()

    u = d.get("users") or {}
    await query.edit_message_text(
        f"🚫 <b>Dépôt rejeté</b>\n\n👤 {u.get('name','—')} ({u.get('phone','—')})\n💰 {fmt(d.get('amount',0))}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Autres dépôts", callback_data="menu_deposits_pending")],
            [InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")],
        ])
    )


# ══════════════════════════════════════════════════════════════════
#  ✅ RETRAITS EN ATTENTE
# ══════════════════════════════════════════════════════════════════
async def show_withdrawals_pending(query):
    res = (
        sb.table("withdrawals")
        .select("*, users(name, phone, ref_code)")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    wits = res.data or []

    if not wits:
        await query.edit_message_text("✅ <b>Aucun retrait en attente</b>",
                                      parse_mode="HTML", reply_markup=back_button())
        return

    text = f"💳 <b>Retraits en attente</b> ({len(wits)})\n\n"
    buttons = []

    for w in wits[:10]:
        u = w.get("users") or {}
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{u.get('name','—')}</b> ({u.get('phone','—')})\n"
            f"💰 Demandé : <b>{fmt(w.get('amount',0))}</b>\n"
            f"💸 Frais : {fmt(w.get('fees',0))} · ✅ À envoyer : <b>{fmt(w.get('net_amount',0))}</b>\n"
            f"📱 {w.get('operator','—')} · {w.get('number','—')}\n"
            f"📅 {fmt_date(w.get('created_at',''))}\n"
        )
        wid = str(w["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Valider #{wid[:6]}", callback_data=f"wit_validate_{wid}"),
            InlineKeyboardButton("❌ Rejeter",             callback_data=f"wit_reject_{wid}"),
        ])

    buttons.append([InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def show_withdrawal_detail(query, wit_id: str):
    res = sb.table("withdrawals").select("*, users(name, phone, ref_code)").eq("id", wit_id).single().execute()
    w = res.data
    if not w:
        await query.edit_message_text("❌ Retrait introuvable.", reply_markup=back_button())
        return
    u = w.get("users") or {}
    text = (
        f"💳 <b>Détail retrait</b>\n\n"
        f"🆔 <code>{w['id']}</code>\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 Demandé : <b>{fmt(w['amount'])}</b>\n"
        f"💸 Frais : {fmt(w.get('fees',0))}\n"
        f"✅ Net : <b>{fmt(w.get('net_amount',0))}</b>\n"
        f"📱 {w.get('operator','—')} · {w.get('number','—')}\n"
        f"📊 {badge_status(w.get('status',''))}\n"
        f"📅 {fmt_date(w.get('created_at',''))}\n"
    )
    buttons = []
    if w.get("status") == "pending":
        buttons.append([
            InlineKeyboardButton("✅ Valider", callback_data=f"wit_validate_{wit_id}"),
            InlineKeyboardButton("❌ Rejeter", callback_data=f"wit_reject_{wit_id}"),
        ])
    buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_withdrawals_pending")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def validate_withdrawal(query, wit_id: str):
    res = sb.table("withdrawals").select("*, users(name, phone)").eq("id", wit_id).single().execute()
    w = res.data
    if not w or w.get("status") != "pending":
        await query.edit_message_text("⚠️ Retrait déjà traité.", reply_markup=back_button())
        return

    sb.table("withdrawals").update({"status": "success"}).eq("id", wit_id).execute()
    sb.table("transactions").update({"status": "success"}) \
      .eq("user_id", w["user_id"]).eq("type", "withdraw").eq("status", "pending").execute()

    u = w.get("users") or {}
    await query.edit_message_text(
        f"✅ <b>Retrait validé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 {fmt(w['amount'])} → Net : <b>{fmt(w.get('net_amount',0))}</b>\n"
        f"📱 {w.get('operator','—')} · {w.get('number','—')}\n\n"
        f"💳 <i>Pensez à envoyer le montant sur MTN MoMo !</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Autres retraits", callback_data="menu_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Menu principal",  callback_data="menu_main")],
        ])
    )


async def reject_withdrawal(query, wit_id: str):
    res = sb.table("withdrawals").select("*, users(name, phone)").eq("id", wit_id).single().execute()
    w = res.data
    if not w:
        await query.edit_message_text("❌ Retrait introuvable.", reply_markup=back_button())
        return

    sb.rpc("increment_balance", {"uid": w["user_id"], "amount": w["amount"]}).execute()
    sb.table("withdrawals").update({"status": "rejected"}).eq("id", wit_id).execute()
    sb.table("transactions").update({"status": "failed"}) \
      .eq("user_id", w["user_id"]).eq("type", "withdraw").eq("status", "pending").execute()

    u = w.get("users") or {}
    await query.edit_message_text(
        f"🚫 <b>Retrait rejeté — solde remboursé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"💰 {fmt(w.get('amount',0))} remboursé",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Autres retraits", callback_data="menu_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Menu principal",  callback_data="menu_main")],
        ])
    )


# ══════════════════════════════════════════════════════════════════
#  COMPTES INACTIFS
# ══════════════════════════════════════════════════════════════════
async def show_inactive_accounts(query):
    res = (
        sb.table("users")
        .select("*")
        .eq("is_active", False)
        .order("created_at", desc=False)
        .execute()
    )
    accounts = res.data or []

    if not accounts:
        await query.edit_message_text("✅ <b>Aucun compte en attente</b>",
                                      parse_mode="HTML", reply_markup=back_button())
        return

    text = f"🔓 <b>Comptes à activer</b> ({len(accounts)})\n\n"
    buttons = []

    for u in accounts[:10]:
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{u.get('name','—')}</b>\n"
            f"📞 {u.get('phone','—')} · Ref: {u.get('ref_code','—')}\n"
            f"📅 {fmt_date(u.get('created_at',''))}\n"
        )
        uid = str(u["id"])
        buttons.append([
            InlineKeyboardButton(f"✅ Activer {u.get('name','').split()[0]}", callback_data=f"acc_activate_{uid}"),
            InlineKeyboardButton("ℹ️ Détail", callback_data=f"acc_detail_{uid}"),
        ])

    buttons.append([InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def show_account_detail(query, uid: str):
    res = sb.table("users").select("*").eq("id", uid).single().execute()
    u = res.data
    if not u:
        await query.edit_message_text("❌ Utilisateur introuvable.", reply_markup=back_button())
        return

    deps = sb.table("deposits").select("amount,status,number,operator") \
             .eq("user_id", uid).eq("status", "pending").execute().data or []
    dep_txt = "".join(
        f"\n  💰 {fmt(d['amount'])} · {d.get('operator','—')} · {d.get('number','—')}"
        for d in deps
    )

    text = (
        f"👤 <b>Détail compte</b>\n\n"
        f"🆔 <code>{u['id']}</code>\n"
        f"📛 <b>{u.get('name','—')}</b>\n"
        f"📞 {u.get('phone','—')} · 🏷️ {u.get('ref_code','—')}\n"
        f"💰 Solde : {fmt(u.get('balance',0))}\n"
        f"📊 {'✅ Actif' if u.get('is_active') else '⏳ Inactif'}\n"
        f"📅 {fmt_date(u.get('created_at',''))}\n"
        + (f"\n📥 Dépôts en attente :{dep_txt}" if dep_txt else "")
    )
    buttons = []
    if not u.get("is_active"):
        buttons.append([InlineKeyboardButton("✅ Activer ce compte", callback_data=f"acc_activate_{uid}")])
    buttons.append([InlineKeyboardButton("⬅️ Retour", callback_data="menu_inactive_accounts")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def activate_account(query, uid: str):
    res = sb.table("users").select("*").eq("id", uid).single().execute()
    u = res.data
    if not u:
        await query.edit_message_text("❌ Utilisateur introuvable.", reply_markup=back_button())
        return
    if u.get("is_active"):
        await query.edit_message_text("⚠️ Compte déjà actif.", reply_markup=back_button())
        return

    sb.table("users").update({"is_active": True}).eq("id", uid).execute()

    parrain_txt = ""
    parent_id = u.get("referred_by")
    if parent_id:
        sb.rpc("increment_balance", {"uid": parent_id, "amount": 2000}).execute()
        sb.table("transactions").insert({
            "user_id": parent_id, "type": "referral", "amount": 2000, "status": "success",
            "meta": {"level": 1, "from_user": uid, "from_name": u.get("name")}
        }).execute()
        parrain_txt += "\n📣 +2 000 FCFA → parrain N1"

        p2 = sb.table("users").select("referred_by").eq("id", parent_id).single().execute()
        gp_id = (p2.data or {}).get("referred_by")
        if gp_id:
            sb.rpc("increment_balance", {"uid": gp_id, "amount": 700}).execute()
            sb.table("transactions").insert({
                "user_id": gp_id, "type": "referral", "amount": 700, "status": "success",
                "meta": {"level": 2, "from_user": uid, "from_name": u.get("name")}
            }).execute()
            parrain_txt += "\n📣 +700 FCFA → parrain N2"

    await query.edit_message_text(
        f"✅ <b>Compte activé</b>\n\n"
        f"👤 {u.get('name','—')} ({u.get('phone','—')})\n"
        f"🏷️ {u.get('ref_code','—')}{parrain_txt}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Autres comptes", callback_data="menu_inactive_accounts")],
            [InlineKeyboardButton("⬅️ Menu principal", callback_data="menu_main")],
        ])
    )


# ══════════════════════════════════════════════════════════════════
#  HISTORIQUES
# ══════════════════════════════════════════════════════════════════
async def show_deposits_history(query):
    deps = sb.table("deposits").select("*, users(name)") \
             .order("created_at", desc=True).limit(15).execute().data or []
    if not deps:
        await query.edit_message_text("📋 Aucun dépôt.", reply_markup=back_button())
        return
    text = "📋 <b>Historique dépôts</b> (15 derniers)\n\n"
    for d in deps:
        u = d.get("users") or {}
        act = "🔓" if d.get("is_activation") else "📥"
        text += f"{act} {badge_status(d.get('status',''))} · <b>{fmt(d['amount'])}</b> · {u.get('name','—')} · {fmt_date(d.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_button())


async def show_withdrawals_history(query):
    wits = sb.table("withdrawals").select("*, users(name)") \
             .order("created_at", desc=True).limit(15).execute().data or []
    if not wits:
        await query.edit_message_text("📋 Aucun retrait.", reply_markup=back_button())
        return
    text = "📋 <b>Historique retraits</b> (15 derniers)\n\n"
    for w in wits:
        u = w.get("users") or {}
        text += f"{badge_status(w.get('status',''))} · <b>{fmt(w['amount'])}</b> (net: {fmt(w.get('net_amount',0))}) · {u.get('name','—')} · {fmt_date(w.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_button())


async def show_all_transactions(query):
    txs = sb.table("transactions").select("*, users(name)") \
            .order("created_at", desc=True).limit(20).execute().data or []
    if not txs:
        await query.edit_message_text("📋 Aucune transaction.", reply_markup=back_button())
        return
    icons = {
        "deposit":"📥", "withdraw":"💳", "bonus":"🎁",
        "ad":"📢", "mission":"🎯", "referral":"👥", "activation":"🔓"
    }
    text = "🔄 <b>Toutes les transactions</b> (20 dernières)\n\n"
    for tx in txs:
        u = tx.get("users") or {}
        ico  = icons.get(tx.get("type",""), "💸")
        sign = "−" if tx.get("type") == "withdraw" else "+"
        text += f"{ico} {sign}{fmt(tx['amount'])} · {badge_status(tx.get('status',''))} · {u.get('name','—')} · {fmt_date(tx.get('created_at',''))}\n"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_button())


# ══════════════════════════════════════════════════════════════════
#  STATISTIQUES
# ══════════════════════════════════════════════════════════════════
async def show_stats(query):
    u_res = sb.table("users").select("id, is_active", count="exact").execute()
    u_all = u_res.count or 0
    u_act = sum(1 for u in (u_res.data or []) if u.get("is_active"))

    d_all  = sb.table("deposits").select("amount, status").execute().data or []
    d_ok   = sum(x["amount"] for x in d_all if x["status"] == "success")
    d_pend = sum(1 for x in d_all if x["status"] == "pending")

    w_all  = sb.table("withdrawals").select("amount, net_amount, status").execute().data or []
    w_ok   = sum(x.get("net_amount", 0) for x in w_all if x["status"] == "success")
    w_pend = sum(1 for x in w_all if x["status"] == "pending")

    tx_all     = sb.table("transactions").select("type, amount, status").execute().data or []
    bonus_t    = sum(x["amount"] for x in tx_all if x["type"] == "bonus"    and x["status"] == "success")
    ad_t       = sum(x["amount"] for x in tx_all if x["type"] == "ad"       and x["status"] == "success")
    mission_t  = sum(x["amount"] for x in tx_all if x["type"] == "mission"  and x["status"] == "success")
    referral_t = sum(x["amount"] for x in tx_all if x["type"] == "referral" and x["status"] == "success")

    ads_count = len(sb.table("ads").select("id").eq("is_active", True).execute().data or [])

    text = (
        f"📊 <b>Statistiques Mind Cash</b>\n\n"
        f"👥 <b>Utilisateurs</b>\n"
        f"  • Total : {u_all} · Actifs : {u_act} · Inactifs : {u_all - u_act}\n\n"
        f"📥 <b>Dépôts validés</b> : {fmt(d_ok)} ({d_pend} en attente)\n"
        f"💳 <b>Retraits envoyés</b> : {fmt(w_ok)} ({w_pend} en attente)\n\n"
        f"💰 <b>Gains distribués</b>\n"
        f"  🎁 Bonus : {fmt(bonus_t)}\n"
        f"  📢 Pubs  : {fmt(ad_t)}\n"
        f"  🎯 Missions : {fmt(mission_t)}\n"
        f"  👥 Parrainage : {fmt(referral_t)}\n\n"
        f"📢 Publicités actives : {ads_count}"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=back_button())


# ══════════════════════════════════════════════════════════════════
#  📢 GESTION DES PUBLICITÉS
# ══════════════════════════════════════════════════════════════════
async def show_ads_menu(query):
    await query.edit_message_text(
        "📢 <b>Gestion des publicités</b>\n\n"
        "Ajoutez ou gérez les publicités affichées sur le site.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Ajouter une publicité", callback_data="ads_add_start")],
            [InlineKeyboardButton("📋 Voir toutes les pubs",  callback_data="ads_list")],
            [InlineKeyboardButton("⬅️ Menu principal",        callback_data="menu_main")],
        ])
    )


async def show_ads_list(query):
    ads = sb.table("ads").select("*").order("created_at", desc=True).execute().data or []
    if not ads:
        await query.edit_message_text(
            "📢 <b>Aucune publicité créée</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Ajouter une pub", callback_data="ads_add_start")],
                [InlineKeyboardButton("⬅️ Retour",          callback_data="menu_ads")],
            ])
        )
        return

    text = f"📢 <b>Publicités ({len(ads)})</b>\n\n"
    buttons = []
    for ad in ads:
        statut = "✅ Active" if ad.get("is_active") else "⏸️ Inactive"
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{ad.get('icon','📢')} <b>{ad.get('title','—')}</b>\n"
            f"⏱ {ad.get('duration_seconds',0)}s · 💰 {fmt(ad.get('reward',0))} · {statut}\n"
        )
        aid = str(ad["id"])
        toggle_lbl = "⏸️ Désactiver" if ad.get("is_active") else "▶️ Activer"
        buttons.append([
            InlineKeyboardButton(f"ℹ️ {ad.get('title','')[:15]}", callback_data=f"ad_detail_{aid}"),
            InlineKeyboardButton(toggle_lbl,                       callback_data=f"ad_toggle_{aid}"),
            InlineKeyboardButton("🗑️",                             callback_data=f"ad_delete_{aid}"),
        ])

    buttons.append([InlineKeyboardButton("➕ Ajouter une pub", callback_data="ads_add_start")])
    buttons.append([InlineKeyboardButton("⬅️ Retour",          callback_data="menu_ads")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def show_ad_detail(query, ad_id: str):
    ad = sb.table("ads").select("*").eq("id", ad_id).single().execute().data
    if not ad:
        await query.edit_message_text("❌ Pub introuvable.", reply_markup=back_button("menu_ads"))
        return
    statut = "✅ Active" if ad.get("is_active") else "⏸️ Inactive"
    text = (
        f"📢 <b>Détail publicité</b>\n\n"
        f"🆔 <code>{ad['id']}</code>\n"
        f"{ad.get('icon','📢')} <b>{ad.get('title','—')}</b>\n"
        f"📝 {ad.get('description','—')}\n"
        f"🔗 Lien : {ad.get('link') or 'Aucun'}\n"
        f"⏱ Durée : {ad.get('duration_seconds',0)} secondes\n"
        f"💰 Récompense : <b>{fmt(ad.get('reward',0))}</b>\n"
        f"📊 Statut : {statut}\n"
        f"📅 {fmt_date(ad.get('created_at',''))}\n"
    )
    toggle_lbl = "⏸️ Désactiver" if ad.get("is_active") else "▶️ Activer"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
        [
            InlineKeyboardButton(toggle_lbl,       callback_data=f"ad_toggle_{ad_id}"),
            InlineKeyboardButton("🗑️ Supprimer",   callback_data=f"ad_delete_{ad_id}"),
        ],
        [InlineKeyboardButton("⬅️ Liste des pubs", callback_data="ads_list")],
    ]))


async def toggle_ad(query, ad_id: str):
    ad = sb.table("ads").select("is_active").eq("id", ad_id).single().execute().data
    if not ad:
        await query.answer("❌ Pub introuvable.", show_alert=True)
        return
    new_state = not ad.get("is_active", True)
    sb.table("ads").update({"is_active": new_state}).eq("id", ad_id).execute()
    state_txt = "✅ activée" if new_state else "⏸️ désactivée"
    await query.answer(f"Pub {state_txt} !", show_alert=True)
    await show_ads_list(query)


async def delete_ad(query, ad_id: str):
    sb.table("ads").delete().eq("id", ad_id).execute()
    await query.answer("🗑️ Publicité supprimée !", show_alert=True)
    await show_ads_list(query)


# ══════════════════════════════════════════════════════════════════
#  📢 AJOUT D'UNE PUB — ConversationHandler (6 étapes)
# ══════════════════════════════════════════════════════════════════
async def ads_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ <b>Nouvelle publicité — Étape 1/6</b>\n\n"
        "Entrez le <b>titre</b> de la publicité :\n"
        "<i>Exemple : Regardez notre vidéo YouTube</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_TITLE


async def ad_get_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_title"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Titre : <b>{ctx.user_data['ad_title']}</b>\n\n"
        f"<b>Étape 2/6</b> — Entrez la <b>description</b> :\n"
        f"<i>Exemple : Regardez 30 secondes et gagnez 150 FCFA</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_DESC


async def ad_get_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_desc"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Description enregistrée.\n\n"
        f"<b>Étape 3/6</b> — Entrez l'<b>icône emoji</b> de la pub :\n"
        f"<i>Exemple : 📢 🎬 📱 🎵 (un seul emoji)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_ICON


async def ad_get_icon(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ad_icon"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Icône : {ctx.user_data['ad_icon']}\n\n"
        f"<b>Étape 4/6</b> — Entrez la <b>durée en secondes</b> :\n"
        f"<i>Exemple : 30</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_DURATION


async def ad_get_duration(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["ad_duration"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Entrez un nombre entier. Ex : 30")
        return AD_DURATION
    await update.message.reply_text(
        f"✅ Durée : {ctx.user_data['ad_duration']}s\n\n"
        f"<b>Étape 5/6</b> — Entrez la <b>récompense en FCFA</b> :\n"
        f"<i>Exemple : 150</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_REWARD


async def ad_get_reward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["ad_reward"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Entrez un nombre entier. Ex : 150")
        return AD_REWARD
    await update.message.reply_text(
        f"✅ Récompense : {fmt(ctx.user_data['ad_reward'])}\n\n"
        f"<b>Étape 6/6</b> — Entrez le <b>lien URL</b> de la pub :\n"
        f"<i>Exemple : https://youtube.com/watch?v=xxx\n"
        f"Tapez <b>aucun</b> si pas de lien.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Annuler", callback_data="ads_cancel")]])
    )
    return AD_LINK


async def ad_get_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    ctx.user_data["ad_link"] = None if raw.lower() in ("aucun", "non", "-", "") else raw

    recap = (
        f"📢 <b>Récapitulatif</b>\n\n"
        f"{ctx.user_data.get('ad_icon','📢')} <b>{ctx.user_data.get('ad_title','—')}</b>\n"
        f"📝 {ctx.user_data.get('ad_desc','—')}\n"
        f"🔗 Lien : {ctx.user_data.get('ad_link') or 'Aucun'}\n"
        f"⏱ Durée : {ctx.user_data.get('ad_duration',0)}s\n"
        f"💰 Récompense : <b>{fmt(ctx.user_data.get('ad_reward',0))}</b>\n\n"
        f"Confirmez-vous l'ajout ?"
    )
    await update.message.reply_text(
        recap,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirmer", callback_data="ads_confirm")],
            [InlineKeyboardButton("❌ Annuler",  callback_data="ads_cancel")],
        ])
    )
    return ConversationHandler.END


async def ads_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = ctx.user_data

    res = sb.table("ads").insert({
        "title":            data.get("ad_title", "Pub"),
        "description":      data.get("ad_desc", ""),
        "icon":             data.get("ad_icon", "📢"),
        "duration_seconds": data.get("ad_duration", 30),
        "reward":           data.get("ad_reward", 100),
        "link":             data.get("ad_link"),
        "is_active":        True,
    }).execute()

    ctx.user_data.clear()

    if res.data:
        await query.edit_message_text(
            f"✅ <b>Publicité ajoutée avec succès !</b>\n\n"
            f"Elle est maintenant visible sur le site.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Voir toutes les pubs", callback_data="ads_list")],
                [InlineKeyboardButton("⬅️ Menu principal",       callback_data="menu_main")],
            ])
        )
    else:
        await query.edit_message_text("❌ Erreur lors de l'ajout.", reply_markup=back_button("menu_ads"))


async def ads_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    await query.edit_message_text(
        "❌ Ajout annulé.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu pubs", callback_data="menu_ads")]])
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════════
#  MAIN — CORRECTION Python 3.14 : asyncio.run() obligatoire
# ══════════════════════════════════════════════════════════════════
async def main_async():
    """Cœur asynchrone : construit et lance le bot Telegram."""
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
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
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu",  cmd_menu))
    app.add_handler(CallbackQueryHandler(ads_confirm, pattern="^ads_confirm$"))
    app.add_handler(CallbackQueryHandler(ads_cancel,  pattern="^ads_cancel$"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    async def set_commands(application):
        await application.bot.set_my_commands([
            BotCommand("start", "Démarrer le bot"),
            BotCommand("menu",  "Afficher le menu admin"),
        ])
    app.post_init = set_commands

    logger.info("🚀 Bot Admin Mind Cash v2 démarré...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    # ── Keep-alive Flask dans un thread daemon ────────────────────
    # Flask tourne dans son propre thread ; le thread principal reste
    # libre pour qu'asyncio.run() puisse créer sa propre event loop.
    t = threading.Thread(target=keep_alive, daemon=True)
    t.start()
    logger.info("🌐 Serveur keep_alive démarré dans un thread daemon")

    # ── CORRECTION PRINCIPALE ─────────────────────────────────────
    # Python 3.10+ (et surtout 3.14) ne crée plus d'event loop
    # implicitement dans le thread principal.
    # asyncio.run() en crée une propre, puis la détruit proprement.
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
