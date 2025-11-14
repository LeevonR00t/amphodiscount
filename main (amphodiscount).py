# bot.py
import logging
import sqlite3
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

DB_NAME = "promo_codes.db"

# ⚠️ ЗАМЕНИТЕ НА ВАШ ТОКЕН!
BOT_TOKEN = "ВАШ_НАСТОЯЩИЙ_ТОКЕН"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount INTEGER NOT NULL,
            is_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at TIMESTAMP NULL
        )
    ''')
    conn.commit()
    conn.close()

def generate_promo_code(length=6):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def add_promo_code(code, discount):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO promo_codes (code, discount) VALUES (?, ?)', (code, discount))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def check_promo_code(code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT discount, is_used, used_at FROM promo_codes WHERE code = ?', (code,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        discount, is_used, used_at = result
        return {'valid': True, 'discount': discount, 'is_used': bool(is_used), 'used_at': used_at}
    return {'valid': False}

def mark_promo_code_used(code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE promo_codes SET is_used = 1, used_at = CURRENT_TIMESTAMP WHERE code = ?', (code,))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎫 Сгенерировать промо-код", callback_data="generate")],
        [InlineKeyboardButton("🔍 Проверить промо-код", callback_data="check")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Добро пожаловать в систему промо-кодов!\n\nВыберите действие:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "generate":
        await generate_promo_handler(update, context)
    elif query.data == "check":
        await context.bot.send_message(chat_id=query.message.chat_id, text="🔍 Введите промо-код для проверки:")
        context.user_data['waiting_for_code'] = True
    elif query.data == "stats":
        await show_stats(update, context)
    elif query.data == "back":
        await start_from_callback(update, context)
    elif query.data.startswith("apply_"):
        code = query.data.replace("apply_", "")
        await apply_promo_code(update, context, code)

async def start_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("🎫 Сгенерировать промо-код", callback_data="generate")],
        [InlineKeyboardButton("🔍 Проверить промо-код", callback_data="check")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👋 Добро пожаловать в систему промо-кодов!\n\nВыберите действие:", reply_markup=reply_markup)

async def generate_promo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("5%", callback_data="discount_5"), InlineKeyboardButton("10%", callback_data="discount_10")],
        [InlineKeyboardButton("15%", callback_data="discount_15"), InlineKeyboardButton("20%", callback_data="discount_20")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text("🎫 Выберите размер скидки для промо-кода:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("🎫 Выберите размер скидки для промо-кода:", reply_markup=reply_markup)

async def discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    discount = int(query.data.split('_')[1])
    
    code = generate_promo_code()
    while not add_promo_code(code, discount):
        code = generate_promo_code()
    
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="generate")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ Новый промо-код создан!\n\n🎫 Код: <code>{code}</code>\n💰 Скидка: {discount}%\n\nСообщите этот код клиенту для получения скидки.",
        reply_markup=reply_markup, parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_code'):
        code = update.message.text.upper().strip()
        result = check_promo_code(code)
        
        if result['valid']:
            if result['is_used']:
                if result['used_at']:
                    used_date = datetime.strptime(result['used_at'], '%Y-%m-%d %H:%M:%S')
                    formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
                    await update.message.reply_text(f"❌ Промо-код <code>{code}</code> уже был использован.\n📅 Дата применения: {formatted_date}", parse_mode='HTML')
                else:
                    await update.message.reply_text(f"❌ Промо-код <code>{code}</code> уже был использован.", parse_mode='HTML')
            else:
                keyboard = [
                    [InlineKeyboardButton("✅ Применить код", callback_data=f"apply_{code}")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"✅ Промо-код действителен!\n💰 Скидка: {result['discount']}%\n\nНажмите кнопку ниже, чтобы применить код:", reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(f"❌ Промо-код <code>{code}</code> не найден.", parse_mode='HTML')
        
        context.user_data['waiting_for_code'] = False

async def apply_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    query = update.callback_query
    await query.answer()
    result = check_promo_code(code)
    
    if result['valid'] and not result['is_used']:
        mark_promo_code_used(code)
        updated_result = check_promo_code(code)
        
        if updated_result['used_at']:
            used_date = datetime.strptime(updated_result['used_at'], '%Y-%m-%d %H:%M:%S')
            formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
            date_info = f"📅 Применен: {formatted_date}"
        else:
            date_info = "📅 Применен: только что"
        
        keyboard = [[InlineKeyboardButton("↩️ Назад в меню", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"🎉 Промо-код успешно применен!\n\n🎫 Код: <code>{code}</code>\n💰 Скидка: {result['discount']}%\n{date_info}\n\nСкидка активирована для клиента!", reply_markup=reply_markup, parse_mode='HTML')
    elif result['valid'] and result['is_used']:
        if result['used_at']:
            used_date = datetime.strptime(result['used_at'], '%Y-%m-%d %H:%M:%S')
            formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
            date_info = f"📅 Дата применения: {formatted_date}"
        else:
            date_info = "📅 Дата применения: ранее"
        
        keyboard = [[InlineKeyboardButton("↩️ Назад в меню", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(f"❌ Промо-код <code>{code}</code> уже был использован ранее.\n{date_info}", reply_markup=reply_markup, parse_mode='HTML')
    else:
        await query.edit_message_text(f"❌ Ошибка: промо-код <code>{code}</code> не найден.", parse_mode='HTML')

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM promo_codes')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM promo_codes WHERE is_used = 1')
    used = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM promo_codes WHERE is_used = 0')
    active = cursor.fetchone()[0]
    
    cursor.execute('SELECT code, discount, used_at FROM promo_codes WHERE is_used = 1 ORDER BY used_at DESC LIMIT 5')
    recent_used = cursor.fetchall()
    conn.close()
    
    stats_text = f"📊 Статистика промо-кодов:\n\n🎫 Всего кодов: {total}\n✅ Активных: {active}\n❌ Использовано: {used}\n\n"
    
    if recent_used:
        stats_text += "🕐 Последние использованные коды:\n"
        for code, discount, used_at in recent_used:
            if used_at:
                used_date = datetime.strptime(used_at, '%Y-%m-%d %H:%M:%S')
                formatted_date = used_date.strftime('%d.%m.%Y %H:%M')
                stats_text += f"• {code} ({discount}%) - {formatted_date}\n"
            else:
                stats_text += f"• {code} ({discount}%) - дата неизвестна\n"
    
    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(stats_text, reply_markup=reply_markup)

async def use_promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        code = context.args[0].upper().strip()
        result = check_promo_code(code)
        
        if result['valid'] and not result['is_used']:
            mark_promo_code_used(code)
            updated_result = check_promo_code(code)
            
            if updated_result['used_at']:
                used_date = datetime.strptime(updated_result['used_at'], '%Y-%m-%d %H:%M:%S')
                formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
                date_info = f"📅 Время применения: {formatted_date}"
            else:
                date_info = "📅 Время применения: только что"
            
            await update.message.reply_text(f"✅ Промо-код применен!\n💰 Скидка: {result['discount']}% активирована!\n{date_info}\n\nСкидка успешно применена к покупке.")
        elif result['valid'] and result['is_used']:
            if result['used_at']:
                used_date = datetime.strptime(result['used_at'], '%Y-%m-%d %H:%M:%S')
                formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
                date_info = f"📅 Дата применения: {formatted_date}"
            else:
                date_info = "📅 Дата применения: ранее"
            
            await update.message.reply_text(f"❌ Промо-код <code>{code}</code> уже был использован.\n{date_info}", parse_mode='HTML')
        else:
            await update.message.reply_text(f"❌ Промо-код <code>{code}</code> не найден.", parse_mode='HTML')
    else:
        await update.message.reply_text("Использование: /use <промо-код>\nПример: /use ABC123")

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("use", use_promo_command))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(generate|check|stats|back)$"))
    application.add_handler(CallbackQueryHandler(discount_handler, pattern="^discount_"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^apply_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен на PythonAnywhere!")
    application.run_polling()

if __name__ == "__main__":
    main()