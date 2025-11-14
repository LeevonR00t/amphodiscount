import logging
import sqlite3
import random
import string
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading

# ⚠️ ЗАМЕНИТЕ НА ВАШ TELEGRAM ID
ALLOWED_USER_IDS = [313642812]  # Ваш Telegram ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

DB_NAME = "promo_codes.db"
BOT_TOKEN = "8253391508:AAHRmV5q-zj24oSpbD-jTKRfsMk5DJ-BuU0"  # ⚠️ ЗАМЕНИТЕ!

# Создаем Flask app для порта
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

def check_access(user_id):
    """Проверка доступа пользователя"""
    return user_id in ALLOWED_USER_IDS

async def restricted_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщение о запрете доступа"""
    if update.callback_query:
        await update.callback_query.answer("❌ У вас нет доступа к этому боту.", show_alert=True)
    else:
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")

def private_only(handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not check_access(user_id):
            await restricted_access(update, context)
            return
        return await handler(update, context)
    return wrapper

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

def get_main_menu_keyboard():
    """Клавиатура главного меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Сгенерировать промо-код", callback_data="generate")],
        [InlineKeyboardButton("🔍 Проверить промо-код", callback_data="check")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ])

def get_back_keyboard(target="main"):
    """Клавиатура с кнопкой Назад"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Назад", callback_data=target)]
    ])

def get_discount_keyboard():
    """Клавиатура выбора скидки"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5%", callback_data="discount_5"), 
         InlineKeyboardButton("10%", callback_data="discount_10")],
        [InlineKeyboardButton("15%", callback_data="discount_15"), 
         InlineKeyboardButton("20%", callback_data="discount_20")],
        [InlineKeyboardButton("↩️ Назад", callback_data="main")]
    ])

@private_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - показывает главное меню"""
    text = "👋 Добро пожаловать в систему промо-кодов!\n\nВыберите действие:"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_main_menu_keyboard())

@private_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "main":
        await start(update, context)
        
    elif query.data == "generate":
        await query.edit_message_text(
            "🎫 Выберите размер скидки для промо-кода:",
            reply_markup=get_discount_keyboard()
        )
        
    elif query.data == "check":
        # Сохраняем состояние ожидания кода
        context.user_data['waiting_for_code'] = True
        context.user_data['last_message_id'] = query.message.message_id
        
        await query.edit_message_text(
            "🔍 Введите промо-код для проверки:\n\n"
            "Просто напишите код в чат (например: ABC123)",
            reply_markup=get_back_keyboard("main")
        )
        
    elif query.data == "stats":
        await show_stats(update, context)
        
    elif query.data.startswith("apply_"):
        code = query.data.replace("apply_", "")
        await apply_promo_code(update, context, code)
        
    elif query.data.startswith("discount_"):
        await discount_handler(update, context)

@private_only 
async def discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора скидки"""
    query = update.callback_query
    await query.answer()
    
    discount = int(query.data.split('_')[1])
    
    # Генерируем уникальный код
    code = generate_promo_code()
    while not add_promo_code(code, discount):
        code = generate_promo_code()
    
    text = (f"✅ Новый промо-код создан!\n\n"
            f"🎫 Код: <code>{code}</code>\n"
            f"💰 Скидка: {discount}%\n\n"
            f"Сообщите этот код клиенту для получения скидки.")
    
    await query.edit_message_text(
        text,
        reply_markup=get_back_keyboard("generate"),
        parse_mode='HTML'
    )

@private_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для проверки кодов"""
    if context.user_data.get('waiting_for_code'):
        code = update.message.text.upper().strip()
        
        # Удаляем сообщение с кодом для чистоты
        try:
            await update.message.delete()
        except:
            pass
        
        result = check_promo_code(code)
        
        if result['valid']:
            if result['is_used']:
                if result['used_at']:
                    used_date = datetime.strptime(result['used_at'], '%Y-%m-%d %H:%M:%S')
                    formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
                    text = (f"❌ Промо-код <code>{code}</code> уже был использован.\n"
                           f"📅 Дата применения: {formatted_date}")
                else:
                    text = f"❌ Промо-код <code>{code}</code> уже был использован."
                
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['last_message_id'],
                    text=text,
                    reply_markup=get_back_keyboard("check"),
                    parse_mode='HTML'
                )
            else:
                # Показываем кнопку применения
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Применить код", callback_data=f"apply_{code}")],
                    [InlineKeyboardButton("↩️ Назад", callback_data="check")]
                ])
                
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['last_message_id'],
                    text=(f"✅ Промо-код действителен!\n"
                          f"💰 Скидка: {result['discount']}%\n\n"
                          f"Нажмите кнопку ниже, чтобы применить код:"),
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data['last_message_id'],
                text=f"❌ Промо-код <code>{code}</code> не найден.",
                reply_markup=get_back_keyboard("check"),
                parse_mode='HTML'
            )
        
        context.user_data['waiting_for_code'] = False

@private_only
async def apply_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """Применение промо-кода"""
    query = update.callback_query
    await query.answer()
    
    result = check_promo_code(code)
    
    if result['valid'] and not result['is_used']:
        # Помечаем код как использованный
        mark_promo_code_used(code)
        
        # Получаем обновленные данные
        updated_result = check_promo_code(code)
        
        if updated_result['used_at']:
            used_date = datetime.strptime(updated_result['used_at'], '%Y-%m-%d %H:%M:%S')
            formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
            date_info = f"📅 Применен: {formatted_date}"
        else:
            date_info = "📅 Применен: только что"
        
        text = (f"🎉 Промо-код успешно применен!\n\n"
                f"🎫 Код: <code>{code}</code>\n"
                f"💰 Скидка: {result['discount']}%\n"
                f"{date_info}\n\n"
                f"Скидка активирована для клиента!")
        
        await query.edit_message_text(
            text,
            reply_markup=get_back_keyboard("main"),
            parse_mode='HTML'
        )
        
    elif result['valid'] and result['is_used']:
        if result['used_at']:
            used_date = datetime.strptime(result['used_at'], '%Y-%m-%d %H:%M:%S')
            formatted_date = used_date.strftime('%d.%m.%Y в %H:%M:%S')
            date_info = f"📅 Дата применения: {formatted_date}"
        else:
            date_info = "📅 Дата применения: ранее"
        
        await query.edit_message_text(
            f"❌ Промо-код <code>{code}</code> уже был использован ранее.\n{date_info}",
            reply_markup=get_back_keyboard("check"),
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text(
            f"❌ Ошибка: промо-код <code>{code}</code> не найден.",
            reply_markup=get_back_keyboard("check"),
            parse_mode='HTML'
        )

@private_only
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику промо-кодов"""
    query = update.callback_query
    await query.answer()
    
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
    
    stats_text = (f"📊 Статистика промо-кодов:\n\n"
                  f"🎫 Всего кодов: {total}\n"
                  f"✅ Активных: {active}\n"
                  f"❌ Использовано: {used}\n\n")
    
    if recent_used:
        stats_text += "🕐 Последние использованные коды:\n"
        for code, discount, used_at in recent_used:
            if used_at:
                used_date = datetime.strptime(used_at, '%Y-%m-%d %H:%M:%S')
                formatted_date = used_date.strftime('%d.%m.%Y %H:%M')
                stats_text += f"• {code} ({discount}%) - {formatted_date}\n"
            else:
                stats_text += f"• {code} ({discount}%) - дата неизвестна\n"
    
    await query.edit_message_text(
        stats_text,
        reply_markup=get_back_keyboard("main")
    )

def run_bot():
    """Запуск Telegram бота"""
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Telegram бот запущен!")
    application.run_polling()

def main():
    """Главная функция - запускает и веб-сервер и бота"""
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("🌐 Веб-сервер запущен на порту 10000")
    
    # Запускаем бота в основном потоке
    run_bot()

if __name__ == "__main__":
    main()
