from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden, BadRequest
import os
import re
import json
import urllib.request
import urllib.parse

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')
# API ключ для Yandex Geocoder
YANDEX_GEOCODER_API_KEY = '0e4655c5-eb37-4f51-8272-f307172a2054'

# ID разрешенных чатов и чата для уведомлений
ALLOWED_CHAT_IDS = [-1003181939785, -1002960326030, -1003231802185]
NOTIFICATION_CHAT_ID = -1003231802185

# Конфигурация ключевых слов для разных чатов
CHAT_KEYWORD_CONFIGS = {
    -1003231802185: {  # Специальный чат
        'keywords': ['карт', 'оклей', 'сигнал'],
        'response': "@{username} Держи карту сигналов и оклейки https://t.me/toc99999/506"
    },
    # Можно добавить конфигурации для других чатов:
    # -1003181939785: {
    #     'keywords': ['поиск', 'потеря', 'найден'],
    #     'response': "@{username} Информация о поисках: ссылка_для_этого_чата"
    # }
}

async def is_allowed_chat(update: Update) -> bool:
    """Проверяет, разрешен ли чат для выполнения команд"""
    chat_id = update.effective_chat.id
    return chat_id in ALLOWED_CHAT_IDS

async def send_notification(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Отправляет уведомление в чат для нотификаций"""
    try:
        await context.bot.send_message(
            chat_id=NOTIFICATION_CHAT_ID,
            text=message
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления: {e}")

async def delete_command_message(update: Update):
    """Удаляет сообщение с командой пользователя"""
    try:
        if update.message.chat.type != 'private':  # Только в группах/каналах
            await update.message.delete()
    except Exception:
        pass  # Игнорируем ошибки при удалении сообщений

def get_address_from_coordinates(lat: float, lon: float) -> str:
    """Получает адрес по координатам через Yandex Geocoder API"""
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        'apikey': YANDEX_GEOCODER_API_KEY,
        'geocode': f"{lon},{lat}",
        'format': 'json',
        'lang': 'ru_RU',
        'results': 1
    }
    
    try:
        # Формируем URL с параметрами
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        # Выполняем запрос
        with urllib.request.urlopen(full_url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # Парсим ответ
            members = data.get('response', {}).get('GeoObjectCollection', {}).get('featureMember', [])
            if members:
                geo_object = members[0].get('GeoObject', {})
                address = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', 'Адрес не найден')
                return address
            else:
                return "Адрес не найден"
                
    except Exception as e:
        return f"Ошибка при получении адреса: {str(e)}"

async def privet_toc9(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение бота"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    # Удаляем сообщение с командой
    await delete_command_message(update)
    
    welcome_text = """
🐕 Привет, я - Мухтар, для своих я просто Муха!

🏡 Я буду помогать с поисками моих друзей потеряшек, чтобы они скорее вернулись домой ✨

📚 Я пока только учусь и выполняю мало команд, но все впереди и я хотел бы расти вместе с группой и ее участниками

📍 Сейчас меня научили запоминать места где мы планируем или уже произвели оклейку местности, чтобы было понятно где и когда была произведена работа.

Просто отправь мне координаты в любом формате, и я создам ссылку на карту и найду адрес!
"""
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_text
    )

def extract_coordinates(text):
    """Извлекает координаты из текста в различных форматах"""
    # Удаляем лишние пробелы и приводим к нижнему регистру для упрощения обработки
    clean_text = ' '.join(text.split()).lower()
    
    # Паттерн 1: "55.90296 с.ш. 37.73217 в.д."
    pattern1 = r'(\d+\.\d+)\s*(?:с\.ш\.|с\.ш|сш)\s*(\d+\.\d+)\s*(?:в\.д\.|в\.д|вд)'
    match1 = re.search(pattern1, clean_text)
    if match1:
        try:
            lat = float(match1.group(1))
            lon = float(match1.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
    
    # Паттерн 2: "55.90296 37.73217" (просто два числа через пробел)
    pattern2 = r'(-?\d+\.\d+)\s+(-?\d+\.\d+)'
    match2 = re.search(pattern2, clean_text)
    if match2:
        try:
            lat = float(match2.group(1))
            lon = float(match2.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
    
    # Паттерн 3: "55.90296, 37.73217" (два числа через запятую)
    pattern3 = r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)'
    match3 = re.search(pattern3, clean_text)
    if match3:
        try:
            lat = float(match3.group(1))
            lon = float(match3.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
    
    return None

def contains_keywords(text, chat_id):
    """Проверяет, содержит ли текст ключевые слова для указанного чата"""
    if chat_id not in CHAT_KEYWORD_CONFIGS:
        return False
    
    text_lower = text.lower()
    keywords = CHAT_KEYWORD_CONFIGS[chat_id]['keywords']
    
    for keyword in keywords:
        if keyword in text_lower:
            return True
    return False

def get_keyword_response(chat_id, username):
    """Возвращает ответ на ключевые слова для указанного чата"""
    if chat_id not in CHAT_KEYWORD_CONFIGS:
        return None
    
    response_template = CHAT_KEYWORD_CONFIGS[chat_id]['response']
    return response_template.format(username=username)

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений - приоритет у координат"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    text = update.message.text
    chat_id = update.effective_chat.id
    user = update.message.from_user
    
    # Сначала проверяем наличие координат (высший приоритет)
    coordinates = extract_coordinates(text)
    if coordinates:
        lat, lon = coordinates
        yandex_map_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
        
        # Получаем адрес
        try:
            address = get_address_from_coordinates(lat, lon)
        except Exception:
            address = None
        
        # Формируем сообщение
        message_text = f"📍 Найдены координаты!\n\n"
        
        if address and "Ошибка" not in address and "не найден" not in address:
            message_text += f"🏠 Адрес: {address}\n\n"
        
        message_text += f"📡 Координаты: {lat:.6f}, {lon:.6f}\n"
        message_text += f"🗺️ Ссылка на Яндекс.Карты: {yandex_map_url}"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text
        )
        return  # Прерываем выполнение, так как координаты имеют приоритет
    
    # Если координатов нет, проверяем ключевые слова для этого чата
    if contains_keywords(text, chat_id):
        username = user.username or user.first_name
        response_text = get_keyword_response(chat_id, username)
        
        if response_text:
            await context.bot.send_message(
                chat_id=chat_id,
                text=response_text
            )

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает добавление бота в новые группы"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Бота добавили в группу
            chat = update.message.chat
            user = update.message.from_user
            
            # Проверяем, не является ли это одним из разрешенных чатов
            if chat.id not in ALLOWED_CHAT_IDS:
                notification_text = (
                    f"🚨 Бота добавили в новую группу:\n"
                    f"• Название: {chat.title}\n"
                    f"• ID: {chat.id}\n"
                    f"• Тип: {chat.type}\n"
                    f"• Пользователь: {user.first_name} "
                    f"(@{user.username or 'нет username'})\n"
                    f"• Время: {update.message.date}"
                )
                await send_notification(context, notification_text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    print(f"Произошла ошибка: {context.error}")

def main():
    """Запуск бота"""
    app = Application.builder().token(token).build()
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Добавляем обработчики команд и сообщений
    app.add_handler(CommandHandler("privet_toc9", privet_toc9))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    
    # Обработчик добавления бота в группы
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    
    print("Бот Мухтар запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()