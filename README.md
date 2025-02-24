# -
Краткое описание функций и обработчиков

load_data():
Загружает данные из файлов JSON (история курсов, настройки пользователей, избранные суммы, история расчетов).
Если файлы не существуют, создает пустые структуры данных.

save_data():
Сохраняет текущие данные в файлы JSON.

get_exchange_rates():
Получает текущие курсы покупки и продажи евро с сайта.
Возвращает кортеж (курс покупки, курс продажи) или (None, None) в случае ошибки.

get_rate_trend():
Определяет тренд курса (рост или падение) на основе последних двух записей в истории.
Возвращает кортеж (тренд покупки, тренд продажи) в виде эмодзи (📈 или 📉).

generate_rate_graph():
Генерирует график изменения курса за последние 24 часа.
Возвращает объект BytesIO с изображением графика или None в случае ошибки.

send_rates():
Отправляет текущие курсы валют в чат, если chat_id установлен.

start():
Обработчик команды /start. Инициализирует chat_id и настройки пользователя.
Отправляет приветственное сообщение и клавиатуру для начала работы.

get_rate_analytics():
Анализирует курсы за сегодняшний день и возвращает строку с минимальным, максимальным и средним значением курсов.

message_handler():
Обработчик текстовых сообщений. Определяет, какая команда была выбрана пользователем, и выполняет соответствующие действия (отправка курсов, расчеты, аналитика и т.д.).

create_flask_app():
Создает Flask-приложение для предоставления API статуса бота и текущих курсов.

run_flask_server():
Запускает Flask-сервер в отдельном потоке.

main():
Основная функция для запуска бота и Flask-сервера.
