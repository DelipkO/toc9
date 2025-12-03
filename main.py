from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden, BadRequest
import os
import re
import json
import urllib.request
import urllib.parse
import time
from collections import defaultdict

# Идентификаторы пользователей:
# Анна 226098861
# Яна 1288551587
# Катя 1385605251
# Сабина 1144271314
# Я 287305832
# Женя 1645755515

# Рута -1003414483458

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')
# API ключ для Yandex Geocoder
YANDEX_GEOCODER_API_KEY = '0e4655c5-eb37-4f51-8272-f307172a2054'

# ID разрешенных чатов и чата для уведомлений
ALLOWED_CHAT_IDS = [-1003181939785, -1002960326030, -1003231802185, -1003179224036, -1003414483458]
NOTIFICATION_CHAT_ID = -1003231802185
TOC_CHAT_ID = -1003231802185  # Чат, для которого используем toc99999 в ссылке и отключаем команду "ищи"
IZUMKI_CHAT_ID = -1003179224036  # Чат Изюмки, для которого используем poisk_izumki в ссылке

# ID пользователей для отслеживания команд "ищи" и для пересылки сообщений
SEARCH_USERS = [1288551587, 1144271314, 1385605251, 287305832]  # Яна, Сабина, Катя, Я
FORWARD_TO_USER_ID = 226098861  # Куда пересылать сообщения "ищи" (Анне)
PRIVATE_MESSAGE_FORWARD_TO = 287305832  # Куда пересылать личные сообщения (мне)

# Словарь для хранения уникальных сообщений карты для каждого чата
MAP_MESSAGES = {
    -1003181939785: """@{username}, вот актуальная карта:

🗺 [Карта Степана](https://yandex.ru/maps/?um=constructor%3A6a8046db678054ae4bb02be22c7e369f982221ccb2f344a2d4dca6ca91ff0f75&source=constructorLink)

📍 На карте:
• Места последних сигналов
• Территория оклейки
• Предполагаемое направление движения Степана по сигналам 

💬 Выходя на оклейку, не забывайте включать геотрекер. Он нарисует ваш путь движения, а я с @AnnaMelostnaya внесем его в карту поиска""",
    
    -1003179224036: """@{username}, вот актуальная карта:

🗺 [Карта сигналов Изюмки](https://yandex.ru/maps/?um=constructor%3A0b0ecb864c3a670cead20c975fecca852eb826e1302233a4c2d6433ce73647b2&source=constructorLink)

🗺 [Карта оклейки Изюмки](https://yandex.ru/maps/?um=constructor%3Ae21cf183b42d2793d0054779c87e1f35786507e87af56ed8c7df5e0b339c2ec2&source=constructorLink)

📍 На картам:
• Места последних сигналов
• Территория оклейки
• Предполагаемое направление движения Изюмки по сигналам 

💬 Выходя на оклейку, не забывайте включать геотрекер. Он нарисует ваш путь движения, а я с @AnnaMelostnaya внесем его в карту поиска"""
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

Доступные команды:
/map - карта сигналов

Просто отправь мне координаты в любом формате, и я создам ссылку на карту и найду адрес!
"""
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_text
    )

async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /map - карта сигналов"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    chat_id = update.effective_chat.id
    user = update.message.from_user
    
    # Удаляем сообщение с командой
    await delete_command_message(update)
    
    # Получаем сообщение для конкретного чата
    if chat_id in MAP_MESSAGES:
        map_text = MAP_MESSAGES[chat_id].format(username=user.username or user.first_name)
    else:
        # Сообщение для чатов без отдельной настройки карты
        map_text = f"""@{user.username or user.first_name}, для этого чата пока нет отдельной карты оклейки 😔

Мои хозяева еще не добавили карту оклейки для искомого пушистика :(

Если вам нужна карта для вашего поиска, обратитесь к @AnnaMelostnaya"""
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=map_text,
        parse_mode='Markdown',
        disable_web_page_preview=True
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

async def handle_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду 'Мухтар, ищи!' от указанных пользователей"""
    if not await is_allowed_chat(update):
        return False
    
    chat_id = update.effective_chat.id
    
    # Для чата -1003231802185 отключаем команду "Мухтар, ищи!"
    if chat_id == TOC_CHAT_ID:
        return False
    
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    # Проверяем, что сообщение от нужного пользователя
    if user_id not in SEARCH_USERS:
        return False
    
    # Приводим текст к нижнему регистру для проверки
    clean_text = text.lower()
    
    # Убираем возможное упоминание бота в начале (если есть)
    if clean_text.startswith('@'):
        # Удаляем первое слово (упоминание)
        parts = clean_text.split(' ', 1)
        if len(parts) > 1:
            clean_text = parts[1].strip()
        else:
            clean_text = ''
    
    # Проверяем, содержит ли текст точную фразу "мухтар, ищи!" с возможными вариациями
    pattern = r'^мухтар[,\s]*ищи[!\s]*$'
    
    if re.match(pattern, clean_text):
        try:
            print(f"Найдена команда 'ищи' от пользователя {user_id} в чате {update.effective_chat.id}")
            
            # Отвечаем в чате
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Команду понял, уже выполняю"
            )
            
            # Получаем информацию для уведомления
            sender_name = update.message.from_user.username or update.message.from_user.first_name
            chat_title = update.effective_chat.title or "Без названия"
            
            # Формируем ссылку на сообщение
            chat_id = update.effective_chat.id
            message_id = update.message.message_id
            
            # Формируем ссылку в зависимости от чата
            if chat_id == TOC_CHAT_ID:
                # Для чата 231802185 используем toc99999
                message_link = f"https://t.me/toc99999/{message_id}"
            elif chat_id == IZUMKI_CHAT_ID:
                # Для чата Изюмки используем poisk_izumki
                message_link = f"https://t.me/poisk_izumki/{message_id}"
            else:
                # Для остальных чатов используем реальный ID (убираем -100)
                chat_id_clean = str(abs(chat_id))
                message_link = f"https://t.me/{chat_id_clean}/{message_id}"
            
            # Формируем уведомление в новом формате
            notification_text = (
                f"🔍 @{sender_name} просит добавить новые точки на карту\n"
                f"Чат: {chat_title}\n"
                f"Ссылка: {message_link}"
            )
            
            # Отправляем уведомление указанному пользователю (Анне)
            await context.bot.send_message(
                chat_id=FORWARD_TO_USER_ID,
                text=notification_text
            )
            
        except Exception as e:
            print(f"Ошибка при обработке команды 'ищи': {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка при обработке команды"
            )
        
        return True  # Сообщение обработано как команда "ищи"
    
    return False  # Сообщение не является командой "ищи"

async def handle_coordinates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик координат в сообщениях"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    # Сначала проверяем, не является ли сообщение командой "ищи"
    if await handle_search_command(update, context):
        return  # Если это команда "ищи", не обрабатываем как координаты
    
    text = update.message.text
    
    # Извлекаем координаты из текста
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
            chat_id=update.effective_chat.id,
            text=message_text
        )

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает личные сообщения боту указанному пользователю"""
    if update.message.chat.type == 'private':
        try:
            # Пересылаем сообщение без отправки подтверждения отправителю
            await context.bot.forward_message(
                chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
        except Exception as e:
            print(f"Ошибка при пересылке личного сообщения: {e}")

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
    app.add_handler(CommandHandler("map", map_command))
    
    # Обработчик личных сообщений (должен быть до общего обработчика текста)
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))
    
    # Обработчик текстовых сообщений в группах (координаты и команда "ищи")
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.ChatType.PRIVATE, handle_coordinates))
    
    # Обработчик добавления бота в группы
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    
    print("Бот Мухтар запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()