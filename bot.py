import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from flask import Flask, request

# === КОНСТАНТЫ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8606071323:AAHf8dHaHjkeomGf18MBEfCp2JRJ5PI2hpY")
DADATA_API_KEY = os.getenv("DADATA_API_KEY", "9c9b98a34b76434b390d1f335ee0d3833efdefa5")
DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app для webhook
app = Flask(__name__)

def get_company_by_inn(inn_value: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {DADATA_API_KEY}"
    }
    payload = {"query": inn_value}

    try:
        response = requests.post(DADATA_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка запроса к DADATA: {e}")
        return None

    if not data.get("suggestions"):
        return None

    company = data["suggestions"][0]["data"]
    company_name = company["name"]["full_with_opf"]
    company_inn = company["inn"]
    address = company["address"]["value"]
    ogrn = company["ogrn"]
    kpp = company.get("kpp", "")
    okved = company.get("okved", "Не указан")
    branch_count = company.get("branch_count", 0)
    branch_type = company.get("branch_type", "")
    status = company["state"]["status"]
    management = company.get("management", {})
    manager_name = management.get("name", "Не указан")
    manager_post = management.get("post", "Не указан")

    status_text = "Действующая" if status == "ACTIVE" else f"{status}"
    btype_text = "Головная организация" if branch_type == "MAIN" else "Филиал"

    text = f"""
<b>{company_name}</b>

ИНН: {company_inn}
ОГРН: {ogrn}
ОКВЕД: {okved}
Количество филиалов: {branch_count}
Тип подразделения: {btype_text}
{' КПП: ' + kpp if kpp else ''}
Адрес: {address}
Статус: {status_text}
Руководитель: {manager_name} ({manager_post})
"""
    return text.strip()

def get_keyboard():
    keyboard = [[InlineKeyboardButton("Новый поиск по ИНН", callback_data="new_search")]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context):
    reply_markup = get_keyboard()
    await update.message.reply_text(
        "Привет! Отправь мне ИНН (10 или 12 цифр), и я найду информацию о компании.\n\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def handle_inn(update: Update, context):
    text = update.message.text.strip()

    if not text.isdigit() or len(text) not in [10, 12]:
        await update.message.reply_text("Пожалуйста, отправь ИНН из 10 или 12 цифр.")
        return

    info = get_company_by_inn(text)

    if info:
        reply_markup = get_keyboard()
        await update.message.reply_text(
            info + "\n\nХотите поискать другую компанию?",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("Компания с таким ИНН не найдена.")

async def new_search_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    reply_markup = get_keyboard()
    await query.message.reply_text(
        "Отлично! Отправь мне ИНН (10 или 12 цифр), и я найду информацию о компании.\n\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def button_menu(update: Update, context):
    reply_markup = get_keyboard()
    await update.message.reply_text(
        "Отправь мне ИНН (10 или 12 цифр), и я найду информацию о компании.\n\n",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

@app.route('/telegram', methods=['POST'])
async def webhook():
    """Обработчик входящих обновлений от Telegram"""
    update = Update.de_json(request.get_json(), application.bot)
    await application.process_update(update)
    return 'OK'

@app.route('/healthz')
def healthz():
    """Health-check эндпоинт для UptimeRobot (предотвращает сон)"""
    return 'OK'

@app.route('/')
def index():
    return 'Bot is alive!'

def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не найден в переменных окружения!")
        return

    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_inn))
    application.add_handler(CallbackQueryHandler(new_search_callback, pattern="new_search"))
    application.add_handler(CommandHandler("menu", button_menu))

    logger.info("Бот запущен...")
    
    # Настройка webhook (выполняется при старте)
    import asyncio
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"https://{render_url}/telegram"
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
        )
        logger.info(f"Webhook установлен: {webhook_url}")

    # Запуск Flask сервера (порт берётся из окружения Render)
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    main()