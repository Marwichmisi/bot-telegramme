import sqlite3
import time
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, Filters, CallbackQueryHandler
import os
import re

# États pour les conversations
SET_TIMEZONE, SET_REMINDER_NAME, SET_REMINDER_TIME, DELETE_CHOOSE, MODIF_CHOOSE, MODIF_FIELD, MODIF_VALUE = range(7)

# Initialiser la base de données
def init_db():
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, timezone TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reminders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, reminder_time INTEGER, is_daily INTEGER)''')
    conn.commit()
    conn.close()

# Gestion du fuseau horaire
def get_user_timezone(user_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_user_timezone(user_id, timezone):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, timezone) VALUES (?, ?)", (user_id, timezone))
    conn.commit()
    conn.close()

# Gestion des rappels
def add_reminder(user_id, name, reminder_time, is_daily=0):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("INSERT INTO reminders (user_id, name, reminder_time, is_daily) VALUES (?, ?, ?, ?)",
              (user_id, name, reminder_time, is_daily))
    conn.commit()
    conn.close()

def get_reminders(user_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("SELECT id, name, reminder_time, is_daily FROM reminders WHERE user_id = ?", (user_id,))
    result = c.fetchall()
    conn.close()
    return result

def delete_reminder(reminder_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def clear_reminders(user_id):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def modify_reminder(reminder_id, field, value):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    if field == "name":
        c.execute("UPDATE reminders SET name = ? WHERE id = ?", (value, reminder_id))
    elif field == "time":
        c.execute("UPDATE reminders SET reminder_time = ? WHERE id = ?", (value, reminder_id))
    conn.commit()
    conn.close()

# Conversion des temps
def local_to_utc(user_timezone, local_time_str):
    try:
        local_tz = pytz.timezone(user_timezone)
        local_time = datetime.strptime(local_time_str, '%Y-%m-%d %H:%M')
        local_time = local_tz.localize(local_time)
        utc_time = local_time.astimezone(pytz.utc)
        return int(utc_time.timestamp())
    except Exception:
        return None

def utc_to_local(user_timezone, timestamp):
    try:
        local_tz = pytz.timezone(user_timezone)
        utc_time = datetime.fromtimestamp(timestamp, tz=pytz.utc)
        local_time = utc_time.astimezone(local_tz)
        return local_time.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return "Heure invalide"

# Commande /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = get_user_timezone(user_id)
    if not timezone:
        await update.message.reply_text("🎉 Bienvenue chez @MySkeddyBot ! Avant de commencer, définis ton fuseau horaire (ex : Europe/Paris) :")
        return SET_TIMEZONE
    await update.message.reply_text("🎉 Salut ! Je suis @MySkeddyBot, ton assistant pour ne rien oublier. Tape /help pour voir ce que je peux faire ! 😊")
    return ConversationHandler.END

# Commande /timezone
async def timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Entre ton fuseau horaire (ex : Europe/Paris, America/New_York) :")
    return SET_TIMEZONE

async def receive_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = update.message.text.strip()
    try:
        pytz.timezone(timezone)
        set_user_timezone(user_id, timezone)
        await update.message.reply_text(f"✅ Fuseau horaire défini à {timezone}. Tape /help pour commencer !")
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text("❌ Fuseau horaire invalide. Réessaie (ex : Europe/Paris).")
        return SET_TIMEZONE
    return ConversationHandler.END

# Commande /setreminder
async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = get_user_timezone(user_id)
    if not timezone:
        await update.message.reply_text("❌ Définis d'abord ton fuseau horaire avec /timezone.")
        return ConversationHandler.END
    await update.message.reply_text("Entre le nom du rappel (ex : Réunion) :")
    return SET_REMINDER_NAME

async def receive_reminder_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reminder_name'] = update.message.text.strip()
    await update.message.reply_text("Entre la date et l’heure (format : YYYY-MM-DD HH:MM, ex : 2025-06-16 14:00) :")
    return SET_REMINDER_TIME

async def receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = get_user_timezone(user_id)
    reminder_time_str = update.message.text.strip()
    if not re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', reminder_time_str):
        await update.message.reply_text("❌ Format invalide. Utilise YYYY-MM-DD HH:MM (ex : 2025-06-16 14:00).")
        return SET_REMINDER_TIME
    reminder_name = context.user_data['reminder_name']
    reminder_timestamp = local_to_utc(timezone, reminder_time_str)
    if reminder_timestamp:
        add_reminder(user_id, reminder_name, reminder_timestamp)
        await update.message.reply_text(f"🎉 Rappel '{reminder_name}' programmé pour {reminder_time_str} !")
    else:
        await update.message.reply_text("❌ Erreur dans la date. Réessaie.")
    return ConversationHandler.END

# Commande /daily
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = get_user_timezone(user_id)
    if not timezone:
        await update.message.reply_text("❌ Définis d'abord ton fuseau horaire avec /timezone.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Utilise : /daily 'nom' 'HH:MM' (ex : /daily Réunion 09:00)")
        return
    name = context.args[0]
    time_str = context.args[1]
    try:
        local_tz = pytz.timezone(timezone)
        now = datetime.now(local_tz)
        reminder_time = datetime.strptime(time_str, '%H:%M').replace(year=now.year, month=now.month, day=now.day)
        if reminder_time < now:
            reminder_time += timedelta(days=1)
        reminder_timestamp = local_to_utc(timezone, reminder_time.strftime('%Y-%m-%d %H:%M'))
        add_reminder(user_id, name, reminder_timestamp, is_daily=1)
        await update.message.reply_text(f"✅ Rappel quotidien '{name}' programmé à {time_str} chaque jour.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {str(e)}. Utilise HH:MM (ex : 09:00).")

# Commande /liste
async def liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    timezone = get_user_timezone(user_id)
    if not timezone:
        await update.message.reply_text("❌ Définis d'abord ton fuseau horaire avec /timezone.")
        return
    reminders = get_reminders(user_id)
    if not reminders:
        await update.message.reply_text("😴 Aucun rappel programmé. Ajoute-en avec /setreminder ou /daily !")
        return
    message = "📋 Tes rappels :\n"
    for reminder in reminders:
        reminder_id, name, timestamp, is_daily = reminder
        local_time = utc_to_local(timezone, timestamp)
        daily_text = " (quotidien)" if is_daily else ""
        message += f"{reminder_id}. {name} - {local_time}{daily_text}\n"
    await update.message.reply_text(message)

# Commande /delete
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reminders = get_reminders(user_id)
    if not reminders:
        await update.message.reply_text("😴 Aucun rappel à supprimer.")
        return
    keyboard = []
    for reminder in reminders:
        reminder_id, name, _, _ = reminder
        keyboard.append([InlineKeyboardButton(f"{name}", callback_data=f"delete_{reminder_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choisis le rappel à supprimer :", reply_markup=reply_markup)
    return DELETE_CHOOSE

async def delete_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data.startswith("delete_"):
        reminder_id = int(data.split("_")[1])
        delete_reminder(reminder_id)
        await query.answer("Rappel supprimé !")
        await query.edit_message_text("✅ Rappel supprimé.")
    return ConversationHandler.END

# Commande /modif
async def modif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reminders = get_reminders(user_id)
    if not reminders:
        await update.message.reply_text("😴 Aucun rappel à modifier.")
        return ConversationHandler.END
    context.user_data['reminders'] = reminders
    keyboard = []
    for reminder in reminders:
        reminder_id, name, _, _ = reminder
        keyboard.append([InlineKeyboardButton(f"{name}", callback_data=f"modif_{reminder_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choisis le rappel à modifier :", reply_markup=reply_markup)
    return MODIF_CHOOSE

async def modif_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    reminder_id = int(data.split("_")[1])
    context.user_data['reminder_id'] = reminder_id
    await query.answer()
    await query.edit_message_text("Que veux-tu modifier ? (nom ou heure)")
    return MODIF_FIELD

async def modif_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = update.message.text.lower()
    if field not in ["nom", "heure"]:
        await update.message.reply_text("❌ Choisis 'nom' ou 'heure'.")
        return MODIF_FIELD
    context.user_data['field'] = field
    if field == "nom":
        await update.message.reply_text("Entre le nouveau nom :")
    else:
        await update.message.reply_text("Entre la nouvelle date et heure (YYYY-MM-DD HH:MM) :")
    return MODIF_VALUE

async def modif_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reminder_id = context.user_data['reminder_id']
    field = context.user_data['field']
    value = update.message.text.strip()
    if field == "nom":
        modify_reminder(reminder_id, "name", value)
        await update.message.reply_text("✅ Nom du rappel modifié !")
    else:
        timezone = get_user_timezone(user_id)
        timestamp = local_to_utc(timezone, value)
        if timestamp:
            modify_reminder(reminder_id, "time", timestamp)
            await update.message.reply_text("✅ Heure du rappel modifiée !")
        else:
            await update.message.reply_text("❌ Format de date invalide (YYYY-MM-DD HH:MM).")
            return MODIF_VALUE
    return ConversationHandler.END

# Commande /clear
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reminders = get_reminders(user_id)
    if not reminders:
        await update.message.reply_text("😴 Aucun rappel à supprimer.")
        return
    keyboard = [
        [InlineKeyboardButton("Oui", callback_data="clear_yes"), InlineKeyboardButton("Non", callback_data="clear_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Veux-tu vraiment supprimer tous tes rappels ?", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "clear_yes":
        user_id = query.from_user.id
        clear_reminders(user_id)
        await query.answer("Tous les rappels supprimés !")
        await query.edit_message_text("✅ Tous les rappels supprimés.")
    elif data == "clear_no":
        await query.answer("Opération annulée.")
        await query.edit_message_text("❌ Opération annulée.")

# Commande /help
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = """
📋 Commandes de @MySkeddyBot :
- /start : Message de bienvenue.
- /timezone : Définir ton fuseau horaire.
- /setreminder : Programmer un rappel unique.
- /daily : Programmer un rappel quotidien.
- /liste : Voir tous tes rappels.
- /delete : Supprimer un rappel.
- /modif : Modifier un rappel.
- /clear : Supprimer tous les rappels.
- /help : Afficher cette aide.
😊 Partage @MySkeddyBot avec tes amis !
"""
    await update.message.reply_text(message)

# Vérifier les rappels
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    current_time = int(time.time())
    c.execute("SELECT id, user_id, name, reminder_time, is_daily FROM reminders WHERE reminder_time <= ?", (current_time,))
    reminders = c.fetchall()
    for reminder in reminders:
        reminder_id, user_id, name, timestamp, is_daily = reminder
        timezone = get_user_timezone(user_id)
        local_time = utc_to_local(timezone, timestamp)
        await context.bot.send_message(chat_id=user_id, text=f"⏰ Rappel : {name} à {local_time}")
        if is_daily:
            local_tz = pytz.timezone(timezone)
            local_time = datetime.fromtimestamp(timestamp, tz=pytz.utc).astimezone(local_tz)
            next_day = local_time + timedelta(days=1)
            next_timestamp = int(next_day.astimezone(pytz.utc).timestamp())
            add_reminder(user_id, name, next_timestamp, is_daily=1)
        delete_reminder(reminder_id)
    conn.close()

def main():
    init_db()
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Conversation pour /timezone
    timezone_conv = ConversationHandler(
        entry_points=[CommandHandler("timezone", timezone), CommandHandler("start", start)],
        states={
            SET_TIMEZONE: [MessageHandler(Filters.text & ~Filters.command, receive_timezone)]
        },
        fallbacks=[]
    )

    # Conversation pour /setreminder
    reminder_conv = ConversationHandler(
        entry_points=[CommandHandler("setreminder", set_reminder)],
        states={
            SET_REMINDER_NAME: [MessageHandler(Filters.text & ~Filters.command, receive_reminder_name)],
            SET_REMINDER_TIME: [MessageHandler(Filters.text & ~Filters.command, receive_reminder_time)]
        },
        fallbacks=[]
    )

    # Conversation pour /delete
    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete)],
        states={
            DELETE_CHOOSE: [CallbackQueryHandler(delete_choose)]
        },
        fallbacks=[]
    )

    # Conversation pour /modif
    modif_conv = ConversationHandler(
        entry_points=[CommandHandler("modif", modif)],
        states={
            MODIF_CHOOSE: [CallbackQueryHandler(modif_choose)],
            MODIF_FIELD: [MessageHandler(Filters.text & ~Filters.command, modif_field)],
            MODIF_VALUE: [MessageHandler(Filters.text & ~Filters.command, modif_value)]
        },
        fallbacks=[]
    )

    app.add_handler(timezone_conv)
    app.add_handler(reminder_conv)
    app.add_handler(delete_conv)
    app.add_handler(modif_conv)
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("liste", liste))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(check_reminders, interval=60)

    app.run_polling()

if __name__ == '__main__':
    main()
