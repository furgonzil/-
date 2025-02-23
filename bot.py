import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import asyncio
from datetime import datetime, timedelta
import json
import os
import matplotlib.pyplot as plt
import io
import config
from flask import Flask, jsonify
from threading import Thread

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

# Токен бота
TOKEN = config.TOKEN

# URL сайта
URL = "http://kantor-zawisza.pl/"

# Глобальные переменные
chat_id = None
scheduler = BackgroundScheduler(timezone="Europe/Minsk")
bot = Bot(token=TOKEN)
is_scheduled = False

# Структура для хранения данных
rate_history = {}
user_settings = {}
favorite_amounts = {}
calculation_history = {}

def load_data():
    """
    Загружает данные из файлов JSON (история курсов, настройки пользователей, избранные суммы, история расчетов).
    Если файлы не существуют, создает пустые структуры данных.
    """
    global rate_history, user_settings, favorite_amounts, calculation_history
    try:
        if os.path.exists('rate_history.json'):
            with open('rate_history.json', 'r') as f:
                rate_history = json.load(f)
        if os.path.exists('user_settings.json'):
            with open('user_settings.json', 'r') as f:
                user_settings = json.load(f)
        if os.path.exists('favorite_amounts.json'):
            with open('favorite_amounts.json', 'r') as f:
                favorite_amounts = json.load(f)
        if os.path.exists('calculation_history.json'):
            with open('calculation_history.json', 'r') as f:
                calculation_history = json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")

def save_data():
    """
    Сохраняет текущие данные (история курсов, настройки пользователей, избранные суммы, история расчетов) в файлы JSON.
    """
    try:
        with open('rate_history.json', 'w') as f:
            json.dump(rate_history, f)
        with open('user_settings.json', 'w') as f:
            json.dump(user_settings, f)
        with open('favorite_amounts.json', 'w') as f:
            json.dump(favorite_amounts, f)
        with open('calculation_history.json', 'w') as f:
            json.dump(calculation_history, f)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def get_exchange_rates():
    """
    Получает текущие курсы покупки и продажи евро с сайта.
    Возвращает кортеж (курс покупки, курс продажи) или (None, None) в случае ошибки.
    """
    try:
        response = requests.get(URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        buy_element = soup.select_one("span.EUR-B strong")
        sell_element = soup.select_one("span.EUR-S strong")

        buy_rate = buy_element.text.strip() if buy_element else None
        sell_rate = sell_element.text.strip() if sell_element else None

        if buy_rate and sell_rate:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            rate_history[current_time] = {"buy": buy_rate, "sell": sell_rate}
            save_data()
            return buy_rate, sell_rate

        logging.error("❌ Не удалось найти курсы на странице.")
        return None, None

    except Exception as e:
        logging.error(f"❌ Ошибка при получении курса: {e}")
        return None, None

def get_rate_trend():
    """
    Определяет тренд курса (рост или падение) на основе последних двух записей в истории.
    Возвращает кортеж (тренд покупки, тренд продажи) в виде эмодзи (📈 или 📉).
    """
    if len(rate_history) < 2:
        return "📊", "📊"
    
    times = sorted(rate_history.keys())
    latest = rate_history[times[-1]]
    previous = rate_history[times[-2]]
    
    buy_trend = "📈" if float(latest["buy"].replace(",", ".")) > float(previous["buy"].replace(",", ".")) else "📉"
    sell_trend = "📈" if float(latest["sell"].replace(",", ".")) > float(previous["sell"].replace(",", ".")) else "📉"
    
    return buy_trend, sell_trend

async def generate_rate_graph():
    """
    Генерирует график изменения курса за последние 24 часа.
    Возвращает объект BytesIO с изображением графика или None в случае ошибки.
    """
    try:
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        filtered_data = {k: v for k, v in rate_history.items() 
                        if datetime.strptime(k, "%Y-%m-%d %H:%M") > day_ago}
        
        if not filtered_data:
            return None
            
        times = sorted(filtered_data.keys())
        buy_rates = [float(filtered_data[t]["buy"].replace(",", ".")) for t in times]
        sell_rates = [float(filtered_data[t]["sell"].replace(",", ".")) for t in times]
        
        plt.figure(figsize=(10, 6))
        plt.plot(range(len(times)), buy_rates, label='Покупка', marker='o')
        plt.plot(range(len(times)), sell_rates, label='Продажа', marker='o')
        
        plt.title('Динамика курса EUR/PLN за 24 часа')
        plt.xlabel('Время')
        plt.ylabel('Курс')
        plt.legend()
        plt.grid(True)
        
        plt.xticks(range(len(times)), 
                  [datetime.strptime(t, "%Y-%m-%d %H:%M").strftime("%H:%M") for t in times], 
                  rotation=45)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
    except Exception as e:
        logging.error(f"Ошибка при создании графика: {e}")
        return None

async def send_rates():
    """
    Отправляет текущие курсы валют в чат, если chat_id установлен.
    """
    global chat_id
    if chat_id:
        buy_rate, sell_rate = get_exchange_rates()
        if buy_rate and sell_rate:
            buy_trend, sell_trend = get_rate_trend()
            message = (
                f"💶 <b>Курс евро:</b>\n\n"
                f"{buy_trend} <b>Покупка:</b> {buy_rate} PLN\n"
                f"{sell_trend} <b>Продажа:</b> {sell_rate} PLN\n\n"
                f"🕒 {datetime.now().strftime('%H:%M')}"
            )
        else:
            message = "❌ Не удалось получить курс евро."
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
    else:
        logging.info("chat_id не установлен.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start. Инициализирует chat_id и настройки пользователя.
    Отправляет приветственное сообщение и клавиатуру для начала работы.
    """
    global chat_id
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in user_settings:
        user_settings[chat_id] = {
            "notifications": True,
            "favorite_amounts": []
        }
        save_data()

    welcome_message = (
        "👋 <b>Добро пожаловать в FURGON EuroBot!</b>\n\n"
        "🤖 Я помогу вам:\n"
        "• Отслеживать курс евро\n"
        "• Производить расчеты\n"
        "• Анализировать тренды\n"
        "• Сохранять избранные суммы\n\n"
        "Нажмите кнопку ниже, чтобы начать."
    )
    
    start_keyboard = ReplyKeyboardMarkup([["🚀 Начать"]], resize_keyboard=True)
    await update.message.reply_text(welcome_message, reply_markup=start_keyboard, parse_mode="HTML")

def get_rate_analytics():
    """
    Анализирует курсы за сегодняшний день и возвращает строку с минимальным, максимальным и средним значением курсов.
    """
    if len(rate_history) < 2:
        return "Недостаточно данных для анализа"
    
    times = sorted(rate_history.keys())
    latest = rate_history[times[-1]]
    
    today = datetime.now().date()
    today_rates = {k: v for k, v in rate_history.items() 
                  if datetime.strptime(k, "%Y-%m-%d %H:%M").date() == today}
    
    if not today_rates:
        return "Нет данных за сегодня"
    
    buy_rates = [float(v["buy"].replace(",", ".")) for v in today_rates.values()]
    sell_rates = [float(v["sell"].replace(",", ".")) for v in today_rates.values()]
    
    analysis = (
        f"📊 <b>Анализ курса за сегодня:</b>\n\n"
        f"📈 <b>Покупка:</b>\n"
        f"Мин: {min(buy_rates):.3f} PLN\n"
        f"Макс: {max(buy_rates):.3f} PLN\n"
        f"Среднее: {sum(buy_rates)/len(buy_rates):.3f} PLN\n\n"
        f"📉 <b>Продажа:</b>\n"
        f"Мин: {min(sell_rates):.3f} PLN\n"
        f"Макс: {max(sell_rates):.3f} PLN\n"
        f"Среднее: {sum(sell_rates)/len(sell_rates):.3f} PLN"
    )
    
    return analysis

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик текстовых сообщений. Определяет, какая команда была выбрана пользователем,
    и выполняет соответствующие действия (отправка курсов, расчеты, аналитика и т.д.).
    """
    global chat_id, is_scheduled
    text = update.message.text
    user_id = str(update.effective_chat.id)

    if text == "🚀 Начать":
        main_keyboard = ReplyKeyboardMarkup([
            ["💶 Текущий курс", "🧮 Калькулятор"],
            ["📊 Аналитика", "⭐️ Избранное"],
            ["⚙️ Настройки"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "🎯 <b>Главное меню</b>\n\nВыберите нужную опцию:",
            reply_markup=main_keyboard,
            parse_mode="HTML"
        )

    elif text == "💶 Текущий курс":
        buy_rate, sell_rate = get_exchange_rates()
        if buy_rate and sell_rate:
            buy_trend, sell_trend = get_rate_trend()
            message = (
                f"💶 <b>Курс евро:</b>\n\n"
                f"{buy_trend} <b>Покупка:</b> {buy_rate} PLN\n"
                f"{sell_trend} <b>Продажа:</b> {sell_rate} PLN\n\n"
                f"🕒 Обновлено {datetime.now().strftime('%H:%M')}"
            )
        else:
            message = "❌ Не удалось получить курс евро."
        await update.message.reply_text(text=message, parse_mode="HTML")

    elif text == "🧮 Калькулятор":
        calc_keyboard = ReplyKeyboardMarkup([
            ["💱 PLN → EUR", "💱 EUR → PLN"],
            ["📋 История расчётов"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "🧮 <b>Калькулятор валют</b>\n\n"
            "Выберите направление конвертации:",
            reply_markup=calc_keyboard,
            parse_mode="HTML"
        )

    elif text == "📊 Аналитика":
        analysis = get_rate_analytics()
        stats_keyboard = ReplyKeyboardMarkup([
            ["📈 График курса"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            analysis,
            reply_markup=stats_keyboard,
            parse_mode="HTML"
        )

    elif text == "⭐️ Избранное":
        if user_id not in favorite_amounts:
            favorite_amounts[user_id] = []
        
        if not favorite_amounts[user_id]:
            message = "У вас пока нет избранных сумм.\nДобавьте их при расчёте, нажав ⭐️"
        else:
            message = "⭐️ <b>Ваши избранные суммы:</b>\n\n"
            buy_rate, sell_rate = get_exchange_rates()
            if buy_rate and sell_rate:
                for amount in favorite_amounts[user_id]:
                    buy_result = amount / float(buy_rate.replace(",", "."))
                    sell_result = amount / float(sell_rate.replace(",", "."))
                    message += (
                        f"💶 {amount:,.2f} PLN\n"
                        f"📈 {buy_result:,.2f} EUR (покупка)\n"
                        f"📉 {sell_result:,.2f} EUR (продажа)\n\n"
                    )
        
        fav_keyboard = ReplyKeyboardMarkup([
            ["🗑 Очистить избранное"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            message,
            reply_markup=fav_keyboard,
            parse_mode="HTML"
        )

    elif text == "⚙️ Настройки":
        if user_id not in user_settings:
            user_settings[user_id] = {"notifications": True}
        
        notifications_status = "включены ✅" if user_settings[user_id]["notifications"] else "выключены ❌"
        settings_keyboard = ReplyKeyboardMarkup([
            ["🔔 Уведомления"],
            ["📊 Управление рассылкой"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        
        await update.message.reply_text(
            f"⚙️ <b>Настройки</b>\n\n"
            f"🔔 Уведомления: {notifications_status}\n\n"
            f"Выберите параметр для настройки:",
            reply_markup=settings_keyboard,
            parse_mode="HTML"
        )

    elif text == "💱 PLN → EUR" or text == "💱 EUR → PLN":
        context.user_data["conversion_mode"] = text
        calc_keyboard = ReplyKeyboardMarkup([
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        currency_from = "PLN" if text == "💱 PLN → EUR" else "EUR"
       
        await update.message.reply_text(
            f"💱 <b>Введите сумму в {currency_from}:</b>",
            reply_markup=calc_keyboard,
            parse_mode="HTML"
        )

    elif text == "📋 История расчётов":
        if user_id not in calculation_history:
            calculation_history[user_id] = []
            
        if not calculation_history[user_id]:
            message = "📋 История расчётов пуста"
        else:
            message = "📋 <b>Последние расчёты:</b>\n\n"
            for calc in calculation_history[user_id][-5:]:  # Показываем последние 5 расчётов
                message += f"{calc}\n\n"
        
        history_keyboard = ReplyKeyboardMarkup([
            ["🗑 Очистить историю"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            message,
            reply_markup=history_keyboard,
            parse_mode="HTML"
        )

    elif text == "📈 График курса":
        graph_buf = await generate_rate_graph()
        if graph_buf:
            await update.message.reply_photo(
                photo=graph_buf,
                caption="📈 График изменения курса за последние 24 часа"
            )
        else:
            await update.message.reply_text("❌ Не удалось сгенерировать график.")

    elif text.replace(".", "").isdigit():
        buy_rate, sell_rate = get_exchange_rates()
        if buy_rate and sell_rate:
            try:
                amount = float(text)
                conversion_mode = context.user_data.get("conversion_mode", "💱 PLN → EUR")
                
                if conversion_mode == "💱 PLN → EUR":
                    buy_result = amount / float(buy_rate.replace(",", "."))
                    sell_result = amount / float(sell_rate.replace(",", "."))
                    message = (
                        f"💱 <b>Результаты расчета:</b>\n\n"
                        f"Сумма: {amount:,.2f} PLN\n\n"
                        f"📈 По курсу покупки:\n{buy_result:,.2f} EUR\n\n"
                        f"📉 По курсу продажи:\n{sell_result:,.2f} EUR"
                    )
                    # Сохраняем в историю
                    if user_id not in calculation_history:
                        calculation_history[user_id] = []
                    calculation_history[user_id].append(
                        f"💶 {amount:,.2f} PLN → EUR\n"
                        f"Покупка: {buy_result:,.2f} EUR\n"
                        f"Продажа: {sell_result:,.2f} EUR"
                    )
                else:
                    buy_result = amount * float(buy_rate.replace(",", "."))
                    sell_result = amount * float(sell_rate.replace(",", "."))
                    message = (
                        f"💱 <b>Результаты расчета:</b>\n\n"
                        f"Сумма: {amount:,.2f} EUR\n\n"
                        f"📈 По курсу покупки:\n{buy_result:,.2f} PLN\n\n"
                        f"📉 По курсу продажи:\n{sell_result:,.2f} PLN"
                    )
                    # Сохраняем в историю
                    if user_id not in calculation_history:
                        calculation_history[user_id] = []
                    calculation_history[user_id].append(
                        f"💶 {amount:,.2f} EUR → PLN\n"
                        f"Покупка: {buy_result:,.2f} PLN\n"
                        f"Продажа: {sell_result:,.2f} PLN"
                    )
                
                context.user_data["last_amount"] = amount
                save_data()

                star_keyboard = ReplyKeyboardMarkup([
                    ["⭐️ Добавить в избранное"],
                    ["⬅️ Вернуться в меню"]
                ], resize_keyboard=True)
                await update.message.reply_text(message, reply_markup=star_keyboard, parse_mode="HTML")
            except ValueError:
                await update.message.reply_text("❌ Ошибка в формате суммы.")
        else:
            await update.message.reply_text("❌ Не удалось получить курс для расчета.")

    elif text == "🗑 Очистить историю":
        if user_id in calculation_history:
            calculation_history[user_id] = []
            save_data()
        await update.message.reply_text(
            "✅ История расчётов очищена",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Вернуться в меню"]], resize_keyboard=True)
        )

    elif text == "⭐️ Добавить в избранное":
        if "last_amount" in context.user_data:
            if user_id not in favorite_amounts:
                favorite_amounts[user_id] = []
            if context.user_data["last_amount"] not in favorite_amounts[user_id]:
                favorite_amounts[user_id].append(context.user_data["last_amount"])
                save_data()
                await update.message.reply_text("✅ Сумма добавлена в избранное!")
            else:
                await update.message.reply_text("ℹ️ Эта сумма уже в избранном.")
        else:
            await update.message.reply_text("❌ Нет суммы для добавления в избранное.")

    elif text == "🗑 Очистить избранное":
        if user_id in favorite_amounts:
            favorite_amounts[user_id] = []
            save_data()
        await update.message.reply_text(
            "✅ Список избранного очищен",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Вернуться в меню"]], resize_keyboard=True)
        )

    elif text == "🔔 Уведомления":
        if user_id not in user_settings:
            user_settings[user_id] = {"notifications": True}
        
        user_settings[user_id]["notifications"] = not user_settings[user_id]["notifications"]
        save_data()
        
        status = "включены ✅" if user_settings[user_id]["notifications"] else "выключены ❌"
        await update.message.reply_text(
            f"🔔 Уведомления {status}",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Вернуться в меню"]], resize_keyboard=True)
        )

    elif text == "📊 Управление рассылкой":
        schedule_keyboard = ReplyKeyboardMarkup([
            ["📱 Включить рассылку" if not is_scheduled else "🚫 Отключить рассылку"],
            ["⬅️ Вернуться в меню"]
        ], resize_keyboard=True)
        status = "включена ✅" if is_scheduled else "отключена ❌"
        await update.message.reply_text(
            f"📊 <b>Управление рассылкой</b>\n\n"
            f"Текущий статус: {status}\n"
            f"Время рассылки: 11:00, 12:00, 15:00, 19:00",
            reply_markup=schedule_keyboard,
            parse_mode="HTML"
        )

    elif text == "📱 Включить рассылку" and not is_scheduled:
        scheduler.remove_all_jobs()
        scheduler.add_job(lambda: asyncio.run(send_rates()), CronTrigger(hour=11, minute=0), id="rate_job_5")
        scheduler.add_job(lambda: asyncio.run(send_rates()), CronTrigger(hour=12, minute=0), id="rate_job_12")
        scheduler.add_job(lambda: asyncio.run(send_rates()), CronTrigger(hour=15, minute=0), id="rate_job_18")
        scheduler.add_job(lambda: asyncio.run(send_rates()), CronTrigger(hour=19, minute=0), id="rate_job_23")
        
        if not scheduler.running:
            scheduler.start()
        
        is_scheduled = True
        await update.message.reply_text(
            "✅ Рассылка успешно включена!\n"
            "Вы будете получать уведомления 4 раза в день.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Вернуться в меню"]], resize_keyboard=True)
        )

    elif text == "🚫 Отключить рассылку" and is_scheduled:
        scheduler.remove_all_jobs()
        is_scheduled = False
        await update.message.reply_text(
            "❌ Рассылка отключена.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Вернуться в меню"]], resize_keyboard=True)
        )

    elif text == "⬅️ Вернуться в меню":
        main_keyboard = ReplyKeyboardMarkup([
            ["💶 Текущий курс", "🧮 Калькулятор"],
            ["📊 Аналитика", "⭐️ Избранное"],
            ["⚙️ Настройки"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "🎯 <b>Главное меню</b>\n\nВыберите нужную опцию:",
            reply_markup=main_keyboard,
            parse_mode="HTML"
        )

def create_flask_app():
    """
    Создает Flask-приложение для предоставления API статуса бота и текущих курсов.
    """
    app = Flask(__name__)

    @app.route('/status')
    def bot_status():
        return jsonify({
            "status": "running",
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_rates": get_exchange_rates()
        })

    @app.route('/rates')
    def get_rates():
        buy_rate, sell_rate = get_exchange_rates()
        return jsonify({
            "buy_rate": buy_rate,
            "sell_rate": sell_rate,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return app

def run_flask_server():
    """
    Запускает Flask-сервер в отдельном потоке.
    """
    app = create_flask_app()
    app.run(host='0.0.0.0', port=5000)

def main():
    """
    Основная функция для запуска бота и Flask-сервера.
    """
    load_data()

    # Запуск Flask-сервера в отдельном потоке
    flask_thread = Thread(target=run_flask_server)
    flask_thread.start()

    # Настройка и запуск Telegram-бота
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.run_polling()

if __name__ == "__main__":
    main()