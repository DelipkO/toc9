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

# Идентификаторы чаты
# Тестирование -1003231802185
# Изюмка -1003179224036
# Рута -1003414483458
# Дубай -1003345143792
# Личный чат тестирования -1003231802185
# Степа -1003181939785

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')
# API ключ для Yandex Geocoder
YANDEX_GEOCODER_API_KEY = '0e4655c5-eb37-4f51-8272-f307172a2054'

# ID разрешенных чатов и чата для уведомлений
ALLOWED_CHAT_IDS = [-1003181939785, -1002960326030, -1003231802185, -1003179224036, -1003414483458, -1003345143792]
NOTIFICATION_CHAT_ID = -1003231802185
TESTING_CHAT_ID = -1003231802185  # Чат для тестирования, где бот не реагирует на команду "ищи"
IZUMKI_CHAT_ID = -1003179224036  # Чат Изюмки, для которого используем poisk_izumki в ссылке
RUTY_CHAT_ID = -1003414483458  # Чат поиска Руты, для которого используем poiskruty в ссылке
DUBAI_CHAT_ID = -1003345143792  # Чат поиска Дубая, для которого используем poisdubai в ссылке

# ID пользователей для отслеживания команд "ищи" и для пересылки сообщений
SEARCH_USERS = [1288551587, 1144271314, 1385605251, 287305832, 1645755515]  # Яна, Сабина, Катя, Я, Женя
FORWARD_TO_USER_ID = 226098861  # Куда пересылать сообщения "ищи" (Анне)
PRIVATE_MESSAGE_FORWARD_TO = 287305832  # Куда пересылать личные сообщения (мне)

# Словарь для хранения уникальных сообщений карты для каждого чата
MAP_MESSAGES = {
    -1003414483458: """@{username}, вот актуальная карта:

🗺 [Карта Руты](https://yandex.ru/maps/?um=constructor%3Ab422530de556f842a2d8624290af0236cada2c7ac296c6ac6e8d3381f8abc7f7&source=constructorLink)

📍 На карте:
• Места последних сигналов
• Территория оклейки
• Предполагаемое направление движения Руты по сигналам 

💬 Выходя на оклейку, не забывайте включать геотрекер. Он нарисует ваш путь движения, а я с @AnnaMelostnaya внесем его в карту поиска""",
    
    -1003179224036: """@{username}, вот актуальная карта:

🗺 [Карта сигналов Изюмки](https://yandex.ru/maps/?um=constructor%3A0b0ecb864c3a670cead20c975fecca852eb826e1302233a4c2d6433ce73647b2&source=constructorLink)

🗺 [Карта оклейки Изюмки](https://yandex.ru/maps/?um=constructor%3Ae21cf183b42d2793d0054779c87e1f35786507e87af56ed8c7df5e0b339c2ec2&source=constructorLink)

📍 На картах:
• Места последних сигналов
• Территория оклейки
• Предполагаемое направление движения Изюмки по сигналам 

💬 Выходя на оклейку, не забывайте включать геотрекер. Он нарисует ваш путь движения, а я с @AnnaMelostnaya внесем его в карту поиска""",
    
    -1003345143792: """@{username}, вот актуальная карта:

🗺 [Карта Дубая](https://yandex.ru/maps/?um=constructor%3A9fcff203e2235b5cbf2bfc4911734b69a677cd5fc3e3868ec3ac3e93758afcf2&source=constructorLink)

📍 На карте:
• Места последних сигналов
• Территория оклейки
• Предполагаемое направление движения Дубая по сигналам 

💬 Выходя на оклейку, не забывайте включать геотрекер. Он нарисует ваш путь движения, а я с @AnnaMelostnaya внесем его в карту поиска"""
}

def generate_message_link(chat_id: int, message_id: int) -> str:
    """Генерирует ссылку на сообщение в зависимости от чата"""
    if chat_id == IZUMKI_CHAT_ID:
        # Для чата Изюмки используем poisk_izumki
        return f"https://t.me/poisk_izumki/{message_id}"
    elif chat_id == RUTY_CHAT_ID:
        # Для чата поиска Руты используем poiskruty
        return f"https://t.me/poiskruty/{message_id}"
    elif chat_id == DUBAI_CHAT_ID:
        # Для чата поиска Дубая используем poisdubai
        return f"https://t.me/poisdubai/{message_id}"
    else:
        # Для остальных чатов используем реальный ID (убираем -100)
        chat_id_clean = str(abs(chat_id))
        return f"https://t.me/{chat_id_clean}/{message_id}"

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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start в личных сообщениях"""
    if update.message.chat.type == 'private':
        user = update.message.from_user
        user_id = user.id
        username = user.username or user.first_name
        
        # Отправляем приветственное сообщение пользователю
        start_text = """Здравствуйте! 

Меня зовут Мухтар, помогаю в поиске собак
Мы будем рады помощи, ищем этих собак:

1. [Дубай] (t.me/poisdubai)
2. [Изюмкa] (t.me/poisk_izumki)
3. [Рута] (t.me/poiskruty)

Если у вас есть вопросы или предложения, пишите @Udashka8 @ldinkais @AnnaMelostnaya @Sabina_F , мы всё рассмотрим"""
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=start_text
        )
        
        # Отправляем уведомление пользователю 287305832 о том, кто запросил /start
        notification_text = (
            f"👤 Кто-то запросил команду /start\n"
            f"ID пользователя: {user_id}\n"
            f"Имя: {user.first_name} {user.last_name or ''}\n"
            f"Username: @{username}"
        )
        
        try:
            await context.bot.send_message(
                chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                text=notification_text
            )
            print(f"Отправлено уведомление о /start от пользователя {user_id}")
        except Exception as e:
            print(f"Ошибка при отправке уведомления о /start: {e}")

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

📚 Я пока только учусь и выполняю мало команд, но все впереди и я хотел бы расти вместе с группя и ее участниками

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
        map_text = f"""@{user.username or user.first_name}, для этого чата пока нет отдельной карта оклейки 😔

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
    
    # Для чата тестирования (-1003231802185) отключаем команду "Мухтар, ищи!"
    if chat_id == TESTING_CHAT_ID:
        return False
    
    user_id = update.message.from_user.id
    
    # Проверяем, что сообщение от нужного пользователя
    if user_id not in SEARCH_USERS:
        return False
    
    text = update.message.text.strip().lower()
    
    # Проверяем, содержит ли текст фразу "мухтар, ищи" (с любыми знаками препинания и регистром)
    # Используем регулярное выражение, которое ищет фразу в любом месте текста
    pattern = r'мухтар[,\s]*ищи'
    
    if re.search(pattern, text):
        try:
            print(f"Найдена команда 'ищи' от пользователя {user_id} в чате {update.effective_chat.id}")
            
            # Отвечаем в чате с новой фразой
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="🗺️✨Новые точки на карте! Иду по следу!🐕🐾"
            )
            
            # Получаем информацию для уведомления
            sender_name = update.message.from_user.username or update.message.from_user.first_name
            chat_title = update.effective_chat.title or "Без названия"
            
            # Формируем ссылку на сообщение
            message_link = generate_message_link(update.effective_chat.id, update.message.message_id)
            
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

async def handle_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает слово 'трекер' в сообщениях"""
    if not await is_allowed_chat(update):
        return False
    
    text = update.message.text.lower()
    
    # Проверяем, содержит ли текст слово "трекер"
    if 'трекер' in text:
        try:
            tracker_text = """[Видеоинструкция: Как пользоваться геотрекером](https://t.me/c/2773274461/34)

Всё показано шаг за шагом! Очень рекомендую."""
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=tracker_text,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            print(f"Отправлена инструкция по трекеру в чат {update.effective_chat.id}")
            
        except Exception as e:
            print(f"Ошибка при отправке инструкции по трекеру: {e}")
        
        return True  # Сообщение обработано как упоминание трекера
    
    return False  # Сообщение не содержит трекер

async def handle_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает ключевые слова (оклеено, сигнал, обклеено) и отправляет уведомление"""
    if not await is_allowed_chat(update):
        return False
    
    text = update.message.text.lower()
    
    # Список ключевых слов и их возможных форм
    keywords = [
        'оклеен', 'оклеено', 'оклеена', 'оклеены', 'оклеенной', 'оклеенные',
        'сигнал', 'сигналы', 'сигналов', 'сигнала', 'сигналу', 'сигналом',
        'обклеен', 'обклеено', 'обклеена', 'обклеены', 'обклеенной', 'обклеенные'
    ]
    
    # Проверяем, содержит ли текст любое из ключевых слов
    found_keywords = [keyword for keyword in keywords if keyword in text]
    
    if found_keywords:
        try:
            print(f"Найдены ключевые слова {found_keywords} в сообщении от {update.message.from_user.id} в чате {update.effective_chat.id}")
            
            # Получаем информацию о чате
            chat_title = update.effective_chat.title or "Без названия"
            sender_name = update.message.from_user.username or update.message.from_user.first_name
            
            # Формируем ссылку на сообщение
            message_link = generate_message_link(update.effective_chat.id, update.message.message_id)
            
            # Формируем уведомление для Анны
            keyword_type = "сигнал" if any(k in ['сигнал', 'сигналы', 'сигналов', 'сигнала', 'сигналу', 'сигналом'] for k in found_keywords) else "оклейка"
            
            notification_text = (
                f"🔍 @{sender_name} сообщает о {keyword_type}\n"
                f"Чат: {chat_title}\n"
                f"Ссылка: {message_link}"
            )
            
            # Отправляем уведомление Анне
            await context.bot.send_message(
                chat_id=FORWARD_TO_USER_ID,
                text=notification_text
            )
            
            print(f"Уведомление о ключевых словах отправлено Анне (ID: {FORWARD_TO_USER_ID})")
            
            # Проверяем, есть ли среди ключевых слов слово "сигнал"
            signal_keywords = ['сигнал', 'сигналы', 'сигналов', 'сигнала', 'сигналу', 'сигналом']
            is_signal = any(signal_keyword in found_keywords for signal_keyword in signal_keywords)
            
            # Если есть слово "сигнал", возвращаем False, чтобы продолжить обработку координатов
            if is_signal:
                print("Сообщение содержит слово 'сигнал', продолжаем обработку координатов")
                return False
            
            # Если нет слова "сигнал", но есть другие ключевые слова (оклеено, обклеено)
            # возвращаем True, чтобы остановить дальнейшую обработку (не отвечать в чате)
            print("Сообщение содержит слова 'оклеено' или 'обклеено', останавливаем обработку")
            return True
            
        except Exception as e:
            print(f"Ошибка при обработке сообщения с ключевым словом: {e}")
        
        return True  # Сообщение обработано, если ошибка - останавливаем обработку
    
    return False  # Ключевые слова не найдены

async def process_coordinates_in_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает координаты в сообщении и отправляет результат в чат"""
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
        return True  # Координаты обработаны
    
    return False  # Координаты не найдены

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает личные сообщения боту"""
    if update.message.chat.type == 'private':
        user_id = update.message.from_user.id
        text = update.message.text
        
        # Проверяем, если сообщение от пользователя 287305832
        if user_id == PRIVATE_MESSAGE_FORWARD_TO:
            # Пытаемся разобрать сообщение как команду отправки в чат
            lines = text.strip().split('\n', 1)
            if len(lines) >= 2:
                chat_identifier = lines[0].strip()
                message_text = lines[1].strip()
                
                try:
                    # Пытаемся понять, что это за идентификатор чата
                    if chat_identifier.startswith('-100'):
                        # Это числовой ID чата
                        chat_id = int(chat_identifier)
                    elif chat_identifier.startswith('@'):
                        # Это username чата
                        # В Telegram API нужно использовать username без @
                        username = chat_identifier[1:]
                        # Отправляем сообщение по username
                        await context.bot.send_message(
                            chat_id=username,
                            text=message_text
                        )
                        # Отправляем подтверждение пользователю
                        await context.bot.send_message(
                            chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                            text=f"✅ Сообщение отправлено в чат {chat_identifier}"
                        )
                        return
                    else:
                        # Пробуем как числовой ID
                        chat_id = int(chat_identifier)
                    
                    # Отправляем сообщение в чат
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message_text
                    )
                    
                    # Отправляем подтверждение пользователю
                    await context.bot.send_message(
                        chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                        text=f"✅ Сообщение отправлено в чат {chat_identifier}"
                    )
                    
                except ValueError as e:
                    # Не удалось преобразовать в число
                    await context.bot.send_message(
                        chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                        text=f"❌ Ошибка: Некорректный формат ID чата. Используйте числовой ID или @username"
                    )
                except Exception as e:
                    # Другие ошибки (бот не в чате, нет прав и т.д.)
                    error_message = str(e)
                    if "Chat not found" in error_message or "chat not found" in error_message:
                        await context.bot.send_message(
                            chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                            text=f"❌ Ошибка: Чат {chat_identifier} не найден или бот не добавлен в него"
                        )
                    elif "Forbidden" in error_message or "bot was kicked" in error_message:
                        await context.bot.send_message(
                            chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                            text=f"❌ Ошибка: Бот не имеет доступа к чату {chat_identifier} или был удален из него"
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                            text=f"❌ Ошибка при отправке сообщения: {error_message}"
                        )
                return
        
        # Для всех остальных пользователей или сообщений не в формате команды
        # пересылаем сообщение пользователю 287305832
        try:
            await context.bot.forward_message(
                chat_id=PRIVATE_MESSAGE_FORWARD_TO,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
        except Exception as e:
            print(f"Ошибка при пересылке личного сообщения: {e}")

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех текстовых сообщений в группах"""
    # Проверяем разрешенный чат
    if not await is_allowed_chat(update):
        return
    
    # Сначала проверяем, не является ли сообщение командой "ищи"
    if await handle_search_command(update, context):
        return  # Если это команда "ищи", не обрабатываем дальше
    
    # Проверяем, не содержит ли сообщение слово "трекер"
    if await handle_tracker(update, context):
        return  # Если это трекер, не обрабатываем дальше
    
    # Проверяем ключевые слова (оклеено, сигнал, обклеено)
    should_stop_processing = await handle_keywords(update, context)
    
    # Если функция handle_keywords вернула True (найдены слова оклеено/обклеено), 
    # то останавливаем обработку и не отвечаем в чате
    if should_stop_processing:
        return
    
    # Проверяем координаты в сообщении
    await process_coordinates_in_message(update, context)

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
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("privet_toc9", privet_toc9))
    app.add_handler(CommandHandler("map", map_command))
    
    # Обработчик личных сообщений (должен быть до общего обработчика текста)
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_private_message))
    
    # Обработчик всех текстовых сообщений в группах (включая команду "ищи", трекер, ключевые слова и координаты)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.ChatType.PRIVATE, handle_all_messages))
    
    # Обработчик добавления бота в группы
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    
    print("Бот Мухтар запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()