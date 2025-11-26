from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden
import os
import re
import aiohttp
import asyncio

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')
# API ключ для Yandex Geocoder
YANDEX_GEOCODER_API_KEY = '0e4655c5-eb37-4f51-8272-f307172a2054'

# ID разрешенных чатов и чата для уведомлений
ALLOWED_CHAT_IDS = [-1003181939785, -1002960326030]
NOTIFICATION_CHAT_ID = -1003231802185

async def is_allowed_chat(update: Update) -> bool:
    """Проверяет, разрешен ли чат для выполнения команд"""
    return update.effective_chat.id in ALLOWED_CHAT_IDS

async def send_notification(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Отправляет уведомление в чат для нотификаций"""
    try:
        await context.bot.send_message(
            chat_id=NOTIFICATION_CHAT_ID,
            text=message
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def delete_command_message(update: Update):
    """Удаляет сообщение с командой пользователя"""
    try:
        if update.message.chat.type != 'private':  # Только в группах/каналах
            await update.message.delete()
    except Forbidden:
        print("Бот не имеет прав для удаления сообщений")
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")

async def get_address_from_coordinates(lat: float, lon: float) -> str:
    """Получает адрес по координатам через Yandex Geocoder API"""
    url = f"https://geocode-maps.yandex.ru/1.x/"
    params = {
        'apikey': YANDEX_GEOCODER_API_KEY,
        'geocode': f"{lon},{lat}",
        'format': 'json',
        'lang': 'ru_RU',
        'results': 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Парсим ответ
                    members = data.get('response', {}).get('GeoObjectCollection', {}).get('featureMember', [])
                    if members:
                        geo_object = members[0].get('GeoObject', {})
                        address = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', 'Адрес не найден')
                        return address
                    else:
                        return "Адрес не найден"
                else:
                    return f"Ошибка API: {response.status}"
                    
    except asyncio.TimeoutError:
        return "Таймаут при получении адреса"
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
    """
    
    await update.message.reply_text(welcome_text)

async def geo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /geo - карта сигналов Степана"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    # Удаляем сообщение с командой
    await delete_command_message(update)
    
    geo_text = """
🗺️ Вот карта сигналов Степана и маршруты где мы его искали:

[Карта сигналов Степана](https://yandex.ru/maps/10716/balashiha/?ll=38.011510%2C55.794242&mode=usermaps&source=constructorLink&um=constructor%3A6a8046db678054ae4bb02be22c7e369f982221ccb2f344a2d4dca6ca91ff0f75&z=14)

📍 На карте отмечены:
• Места последних сигналов
• Маршруты поисковых групп
• Предполагаемое направление движения
"""
    
    await update.message.reply_text(geo_text, parse_mode='Markdown')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        # Если это не разрешенный чат, отправляем уведомление
        if update.message.chat.type in ['group', 'supergroup']:
            await send_notification(
                context,
                f"🚨 Бота добавили в новую группу:\n"
                f"• Название: {update.message.chat.title}\n"
                f"• ID: {update.message.chat.id}\n"
                f"• Тип: {update.message.chat.type}\n"
                f"• Пользователь: {update.message.from_user.first_name} (@{update.message.from_user.username})"
            )
        return
    
    # Удаляем сообщение с командой
    await delete_command_message(update)
    
    start_text = """
🐕 Привет! Я бот Мухтар - помощник в поисках потерянных животных.

Доступные команды:
/start - начать работу
/geo - карта сигналов Степана
/privet_toc9 - информация о боте

Просто отправь мне координаты в любом формате, и я создам ссылку на карту и найду адрес!
"""
    await update.message.reply_text(start_text)

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

async def handle_coordinates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик координат в сообщениях"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    text = update.message.text
    
    # Извлекаем координаты из текста
    coordinates = extract_coordinates(text)
    if coordinates:
        lat, lon = coordinates
        yandex_map_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
        
        # Получаем адрес
        address = await get_address_from_coordinates(lat, lon)
        
        # Формируем сообщение
        message_text = f"📍 Найдены координаты!\n\n"
        
        if address and "Ошибка" not in address and "не найден" not in address:
            message_text += f"🏠 Адрес: {address}\n\n"
        
        message_text += f"📡 Координаты: {lat:.6f}, {lon:.6f}\n"
        message_text += f"🗺️ Ссылка на Яндекс.Карты: {yandex_map_url}"
        
        await update.message.reply_text(message_text)

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает добавление бота в новые группы"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # Бота добавили в группу
            chat = update.message.chat
            user = update.message.from_user
            
            # Проверяем, не является ли это одним из разрешенных чатов
            if chat.id not in ALLOWED_CHAT_IDS:
                await send_notification(
                    context,
                    f"🚨 Бота добавили в новую группу:\n"
                    f"• Название: {chat.title}\n"
                    f"• ID: {chat.id}\n"
                    f"• Тип: {chat.type}\n"
                    f"• Пользователь: {user.first_name} (@{user.username})\n"
                    f"• Время: {update.message.date}"
                )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    print(f"Произошла ошибка: {context.error}")

def main():
    """Запуск бота"""
    app = Application.builder().token(token).build()
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Добавляем обработчики команд и сообщений
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("privet_toc9", privet_toc9))
    app.add_handler(CommandHandler("geo", geo_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coordinates))
    
    # Обработчик добавления бота в группы
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    
    print("Бот Мухтар запущен...")
    print(f"Разрешенные чаты: {ALLOWED_CHAT_IDS}")
    print(f"Чат для уведомлений: {NOTIFICATION_CHAT_ID}")
    print(f"Yandex Geocoder API ключ: {'установлен' if YANDEX_GEOCODER_API_KEY else 'отсутствует'}")
    app.run_polling()

if __name__ == '__main__':
    main()