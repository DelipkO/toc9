from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import os
from datetime import datetime, timedelta
import asyncio
import re

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')

# ID целевого чата
TARGET_CHAT_ID = "@toc99999"

# Хранилище мест для оклейки
places = []
# Временные данные для текущих процессов
temp_data = {}
# Очередь заявок на подтверждение
pending_requests = []

# Белый список пользователей с полными правами
WHITELIST_USERS = [287305832]

# Специальные пользователи (загрузка файлов + уведомления + подтверждение заявок)
FILE_UPLOAD_USERS = [1645755515, 287305832]

# Таймауты для разных процессов (в секундах)
DIALOG_TIMEOUT = 60  # 1 минута для обычных диалогов
REQUEST_APPROVAL_TIMEOUT = 24 * 60 * 60  # 24 часа для подтверждения заявок
FILE_UPLOAD_TIMEOUT = 10 * 60  # 10 минут для загрузки файлов

def is_whitelisted(user_id: int) -> bool:
    """Проверяет, находится ли пользователь в белом списке"""
    return user_id in WHITELIST_USERS

def is_file_upload_user(user_id: int) -> bool:
    """Проверяет, является ли пользователь специальным пользователем"""
    return user_id in FILE_UPLOAD_USERS

async def is_user_in_target_chat(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, состоит ли пользователь в целевой группе"""
    try:
        chat_member = await context.bot.get_chat_member(chat_id=TARGET_CHAT_ID, user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки членства в группе: {e}")
        return False

async def check_group_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет членство в группе и отправляет сообщение если не состоит"""
    user_id = update.effective_user.id
    
    if not await is_user_in_target_chat(user_id, context):
        await send_private_message(
            update,
            context,
            f"❌ Для использования команд бота необходимо состоять в группе {TARGET_CHAT_ID}\n\n"
            f"Пожалуйста, присоединитесь к группе и попробуйте снова."
        )
        return False
    return True

async def start_dialog_timeout(user_id: int, context: ContextTypes.DEFAULT_TYPE, process_type: str = None):
    """Запускает таймер завершения диалога с учетом типа процесса"""
    if user_id in temp_data:
        # Отменяем предыдущий таймер, если есть
        if 'timeout_task' in temp_data[user_id]:
            temp_data[user_id]['timeout_task'].cancel()
        
        # Определяем таймаут в зависимости от типа процесса и пользователя
        if is_file_upload_user(user_id):
            if process_type == 'request_approval':
                timeout_seconds = REQUEST_APPROVAL_TIMEOUT
                timeout_type = "24 часа"
            elif process_type == 'file_upload':
                timeout_seconds = FILE_UPLOAD_TIMEOUT
                timeout_type = "10 минут"
            else:
                timeout_seconds = DIALOG_TIMEOUT
                timeout_type = "60 секунд"
        else:
            timeout_seconds = DIALOG_TIMEOUT
            timeout_type = "60 секунд"
        
        # Сохраняем информацию о таймауте
        temp_data[user_id]['current_timeout'] = timeout_seconds
        temp_data[user_id]['timeout_type'] = timeout_type
        
        # Запускаем новый таймер
        temp_data[user_id]['timeout_task'] = asyncio.create_task(
            dialog_timeout_handler(user_id, context, timeout_seconds, timeout_type)
        )
        temp_data[user_id]['last_activity'] = datetime.now()

async def dialog_timeout_handler(user_id: int, context: ContextTypes.DEFAULT_TYPE, timeout_seconds: int, timeout_type: str):
    """Обработчик таймаута диалога"""
    try:
        await asyncio.sleep(timeout_seconds)
        
        if user_id in temp_data:
            # Проверяем, было ли активность за последние timeout_seconds секунд
            time_since_activity = datetime.now() - temp_data[user_id].get('last_activity', datetime.now())
            
            if time_since_activity.total_seconds() >= timeout_seconds:
                await finish_dialog_timeout(user_id, context, timeout_type)
                
    except asyncio.CancelledError:
        # Таймер был отменен - это нормально
        pass
    except Exception as e:
        print(f"Ошибка в обработчике таймаута: {e}")

async def finish_dialog_timeout(user_id: int, context: ContextTypes.DEFAULT_TYPE, timeout_type: str):
    """Завершает диалог по таймауту"""
    if user_id in temp_data:
        try:
            # Отправляем сообщение о таймауте
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Время обработки истекло ({timeout_type}). Пожалуйста, начните заново, если необходимо."
            )
            
            # Удаляем последнее сообщение бота, если есть
            if 'last_message_id' in temp_data[user_id]:
                try:
                    await context.bot.delete_message(
                        chat_id=user_id,
                        message_id=temp_data[user_id]['last_message_id']
                    )
                except Exception as e:
                    print(f"Ошибка удаления сообщения при таймауте: {e}")
                    
        except Exception as e:
            print(f"Ошибка отправки сообщения о таймауте: {e}")
        
        # Очищаем временные данные
        cleanup_user_data(user_id)

def cleanup_user_data(user_id: int):
    """Очищает временные данные пользователя"""
    if user_id in temp_data:
        # Отменяем таймер, если есть
        if 'timeout_task' in temp_data[user_id]:
            try:
                temp_data[user_id]['timeout_task'].cancel()
            except:
                pass
        del temp_data[user_id]

async def update_user_activity(user_id: int):
    """Обновляет время последней активности пользователя"""
    if user_id in temp_data:
        temp_data[user_id]['last_activity'] = datetime.now()

async def delete_message_after_delay(chat_id: int, message_id: int, context: ContextTypes.DEFAULT_TYPE, delay: int = 10):
    """Удаляет сообщение через указанную задержку"""
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        pass

async def delete_bot_message_safe(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int = None):
    """Безопасное удаление сообщений бота"""
    try:
        if message_id:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message_id)
    except Exception as e:
        pass

async def send_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, process_type: str = None):
    """Отправляет сообщение только тому пользователю, который взаимодействует с ботом"""
    user_id = update.effective_user.id
    
    try:
        message = await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup
        )
        
        if user_id not in temp_data:
            temp_data[user_id] = {}
        temp_data[user_id]['last_message_id'] = message.message_id
        
        # Запускаем/обновляем таймер диалога с учетом типа процесса
        await start_dialog_timeout(user_id, context, process_type)
        
        return message
    except Exception as e:
        print(f"Не удалось отправить сообщение в личку: {e}")
        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup
        )
        
        if user_id not in temp_data:
            temp_data[user_id] = {}
        temp_data[user_id]['last_message_id'] = message.message_id
        
        # Запускаем/обновляем таймер диалога с учетом типа процесса
        await start_dialog_timeout(user_id, context, process_type)
        
        return message

async def send_target_chat_message(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Отправляет сообщение в целевой чат"""
    try:
        message = await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=text
        )
        return message
    except Exception as e:
        print(f"Ошибка отправки в целевой чат: {e}")
        return None

async def send_notification_to_special_users(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Отправляет уведомление специальным пользователям"""
    for user_id in FILE_UPLOAD_USERS:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

async def send_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Отправляет сообщение в групповой чат"""
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text
    )
    return message

async def privet_toc9(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение бота"""
    welcome_text = """
🐕 Привет, я - Мухтар, для своих я просто Муха!

🏡 Я буду помогать с поисками моих друзей потеряшек, чтобы они скорее вернулись домой ✨

📚 Я пока только учусь и выполняю мало команд, но все впереди и я хотел бы расти вместе с группой и ее участниками

📍 Сейчас меня научили запоминать места где мы планируем или уже произвели оклейку местности, чтобы было понятно где и когда была произведена работа.
    """
    
    await send_group_message(update, context, welcome_text)

async def s(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает кнопки управления (доступно всем, но требует членства в группе)"""
    # Проверяем членство в группе
    if not await check_group_membership(update, context):
        asyncio.create_task(delete_message_after_delay(
            update.effective_chat.id, 
            update.message.message_id,
            context,
            1
        ))
        return
    
    user_id = update.effective_user.id
    user_is_whitelisted = is_whitelisted(user_id)
    user_is_file_uploader = is_file_upload_user(user_id)
    
    # Базовая клавиатура для всех пользователей
    base_keyboard = [
        [
            InlineKeyboardButton("📍 Выбрать место для оклейки", callback_data="user_choose_place"),
        ],
        [
            InlineKeyboardButton("❌ Список неоклеенных", callback_data="list_not_pasted"),
            InlineKeyboardButton("📊 Весь список", callback_data="list_all"),
        ]
    ]
    
    if user_is_whitelisted:
        # Администраторы видят все кнопки + базовые
        keyboard = [
            [
                InlineKeyboardButton("📍 Добавить места", callback_data="add_place"),
                InlineKeyboardButton("📝 Назначить ответственного", callback_data="assign_responsible"),
            ],
            [
                InlineKeyboardButton("✅ Подтвердить оклейку", callback_data="confirm_pasting"),
                InlineKeyboardButton("🗑️ Удалить место", callback_data="delete_place"),
            ],
            [
                InlineKeyboardButton("⏳ Заявки на подтверждение", callback_data="view_pending_requests"),
            ]
        ] + base_keyboard
    elif user_is_file_uploader:
        # Специальный пользователь видит кнопки подтверждения с файлами + базовые + отмену ответственного + заявки
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить оклейку с файлами", callback_data="confirm_pasting_with_files"),
                InlineKeyboardButton("❌ Отменить ответственного", callback_data="cancel_responsible"),
            ],
            [
                InlineKeyboardButton("⏳ Заявки на подтверждение", callback_data="view_pending_requests"),
            ]
        ] + base_keyboard
    else:
        # Обычные пользователи видят только базовые кнопки
        keyboard = base_keyboard
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_private_message(
        update, 
        context, 
        "🤖 Выберите действие:",
        reply_markup=reply_markup
    )
    
    asyncio.create_task(delete_message_after_delay(
        update.effective_chat.id, 
        update.message.message_id,
        context,
        1
    ))

async def p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все населенные пункты (доступно всем, но требует членства в группе)"""
    # Проверяем членство в группе
    if not await check_group_membership(update, context):
        asyncio.create_task(delete_message_after_delay(
            update.effective_chat.id, 
            update.message.message_id,
            context,
            1
        ))
        return
    
    user_id = update.effective_user.id
    user_is_file_uploader = is_file_upload_user(user_id)
    
    if not places:
        if user_is_file_uploader:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты"
            )
        else:
            await send_target_chat_message(
                context, 
                "❌ Сначала добавьте населенные пункты"
            )
        
        asyncio.create_task(delete_message_after_delay(
            update.effective_chat.id, 
            update.message.message_id,
            context,
            1
        ))
        return
    
    sorted_places = sorted(places, key=lambda x: x['name'])
    
    # Для специального пользователя показываем расширенный список с возможностью выбора
    if user_is_file_uploader and update.effective_chat.type == 'private':
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            files_info = f" 📎{len(place.get('files', []))} файлов" if place.get('files') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}{files_info}")
        
        await send_private_message(
            update,
            context,
            f"📊 Все населенные пункты:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта для просмотра загруженных файлов:"
        )
        
        temp_data[user_id] = {
            'process': 'view_files',
            'step': 'select_place',
            'sorted_places': sorted_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    else:
        # Стандартное поведение для остальных
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        completed_count = sum(1 for p in places if p.get('completed', False))
        total_count = len(places)
        
        await send_target_chat_message(
            context, 
            f"📊 Все населенные пункты ({completed_count}/{total_count} оклеено):\n" + "\n".join(places_list)
        )
    
    asyncio.create_task(delete_message_after_delay(
        update.effective_chat.id, 
        update.message.message_id,
        context,
        1
    ))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_is_whitelisted = is_whitelisted(user_id)
    user_is_file_uploader = is_file_upload_user(user_id)
    
    # Обновляем активность пользователя
    await update_user_activity(user_id)
    
    # Проверяем членство в группе для всех пользователей
    if not await is_user_in_target_chat(user_id, context):
        await query.edit_message_text(
            text=f"❌ Для использования бота необходимо состоять в группе {TARGET_CHAT_ID}\n\n"
                 f"Пожалуйста, присоединитесь к группе и попробуйте снова."
        )
        return
    
    # Обработка заявок на подтверждение (доступно только специальным пользователям)
    if query.data.startswith('approve_') or query.data.startswith('reject_'):
        if not user_is_file_uploader:
            await query.edit_message_text(text="❌ У вас нет прав для подтверждения заявок.")
            return
        await handle_pending_request(update, context)
        return
    
    if query.data.startswith('view_request_'):
        if not user_is_file_uploader:
            await query.edit_message_text(text="❌ У вас нет прав для просмотра заявок.")
            return
        await view_pending_request_details(update, context)
        return
    
    admin_functions = ["add_place", "assign_responsible", "confirm_pasting", "delete_place"]
    if query.data in admin_functions and not user_is_whitelisted:
        await query.edit_message_text(text="❌ У вас нет прав для использования этой функции.")
        return
    
    if user_id in temp_data and 'last_message_id' in temp_data[user_id]:
        try:
            await delete_bot_message_safe(update, context, temp_data[user_id]['last_message_id'])
        except:
            pass
    
    if query.data == "add_place":
        temp_data[user_id] = {
            'process': 'addplace',
            'step': 'name'
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
        
        await send_private_message(
            update,
            context,
            "📍 Введите наименования населенных пунктов, которые необходимо оклеить.\n\n"
            "Можно ввести несколько названий через запятую или каждое с новой строки:\n"
            "Пример: Москва, Санкт-Петербург, Казань\n"
            "Или:\nМосква\nСанкт-Петербург\nКазань"
        )
    
    elif query.data == "assign_responsible":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        await send_private_message(
            update,
            context,
            f"📝 Населенные пункты:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта для назначения:"
        )
        
        temp_data[user_id] = {
            'process': 'placeconf',
            'step': 'select_place',
            'sorted_places': sorted_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "confirm_pasting":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        await send_private_message(
            update,
            context,
            f"✅ Населенные пункты для подтверждения оклейки:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта, который оклеен:"
        )
        
        temp_data[user_id] = {
            'process': 'placeplus',
            'step': 'select_place',
            'sorted_places': sorted_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "confirm_pasting_with_files":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        await send_private_message(
            update,
            context,
            f"✅ Населенные пункты для подтверждения оклейки с файлами:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта, который оклеен:"
        )
        
        temp_data[user_id] = {
            'process': 'placeplus_with_files',
            'step': 'select_place',
            'sorted_places': sorted_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "cancel_responsible":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        # Фильтруем места: только те, где назначен ответственный, но оклейка еще не произведена
        sorted_places = sorted(places, key=lambda x: x['name'])
        places_with_responsible = [p for p in sorted_places if p.get('user') and not p.get('completed', False)]
        
        if not places_with_responsible:
            await send_private_message(
                update,
                context,
                "✅ Нет мест с назначенными ответственными, где оклейка еще не произведена!"
            )
            return
        
        places_list = []
        for i, place in enumerate(places_with_responsible, 1):
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']}{user_info}{date_info}")
        
        await send_private_message(
            update,
            context,
            f"❌ Места с назначенными ответственными (оклейка не произведена):\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта для отмены ответственного:"
        )
        
        temp_data[user_id] = {
            'process': 'cancel_responsible',
            'step': 'select_place',
            'sorted_places': places_with_responsible
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "user_choose_place":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        # Показываем только места без ответственного и не оклеенные
        available_places = [p for p in sorted_places if not p.get('user') and not p.get('completed', False)]
        
        if not available_places:
            await send_private_message(
                update,
                context,
                "✅ Все населенные пункты уже оклеены или на них назначены ответственные!"
            )
            return
        
        places_list = []
        for i, place in enumerate(available_places, 1):
            places_list.append(f"{i}. {place['name']}")
        
        await send_private_message(
            update,
            context,
            f"📍 Выберите населенный пункт для оклейки:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта, который хотите оклеить:"
        )
        
        temp_data[user_id] = {
            'process': 'user_choose_place',
            'step': 'select_place',
            'sorted_places': available_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "list_not_pasted":
        if not places:
            await send_target_chat_message(
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        not_completed_places = [p for p in sorted_places if not p.get('completed', False)]
        
        if not not_completed_places:
            await send_target_chat_message(
                context,
                "✅ Все населенные пункты уже оклеены!"
            )
            return
        
        places_list = []
        for i, place in enumerate(not_completed_places, 1):
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']}{user_info}{date_info}")
        
        await send_target_chat_message(
            context,
            f"❌ Населенные пункты, где еще не оклеено:\n" + "\n".join(places_list)
        )
    
    elif query.data == "list_all":
        if not places:
            await send_target_chat_message(
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        completed_count = sum(1 for p in places if p.get('completed', False))
        total_count = len(places)
        
        await send_target_chat_message(
            context,
            f"📊 Все населенные пункты ({completed_count}/{total_count} оклеено):\n" + "\n".join(places_list)
        )
    
    elif query.data == "delete_place":
        if not places:
            await send_private_message(
                update,
                context,
                "❌ Сначала добавьте населенные пункты с помощью кнопки '📍 Добавить места'"
            )
            return
        
        sorted_places = sorted(places, key=lambda x: x['name'])
        
        places_list = []
        for i, place in enumerate(sorted_places, 1):
            status = "✅" if place.get('completed', False) else "❌"
            user_info = f" - {place['user']}" if place.get('user') else ""
            date_info = f" ({place['date']})" if place.get('date') else ""
            places_list.append(f"{i}. {place['name']} {status}{user_info}{date_info}")
        
        await send_private_message(
            update,
            context,
            f"🗑️ Населенные пункты:\n" + "\n".join(places_list) + 
            f"\n\nВведите номер населенного пункта для удаления:"
        )
        
        temp_data[user_id] = {
            'process': 'deleteplace',
            'step': 'select_place',
            'sorted_places': sorted_places
        }
        
        # Запускаем таймер диалога
        await start_dialog_timeout(user_id, context)
    
    elif query.data == "view_pending_requests":
        if not user_is_file_uploader:
            await query.edit_message_text(text="❌ У вас нет прав для просмотра заявок.")
            return
        
        # Для специальных пользователей устанавливаем увеличенный таймаут для работы с заявками
        await start_dialog_timeout(user_id, context, 'request_approval')
        await show_pending_requests(update, context)

async def handle_pending_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждения/отклонения заявок"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    # Обновляем активность пользователя
    await update_user_activity(user_id)
    
    if data.startswith('approve_'):
        request_id = int(data.split('_')[1])
        request = next((r for r in pending_requests if r['id'] == request_id), None)
        
        if not request:
            await query.edit_message_text(text="❌ Заявка не найдена или уже обработана.")
            return
        
        # Находим место и назначаем пользователя
        place_index = request['place_index']
        places[place_index]['user'] = request['user_name']
        places[place_index]['date'] = f"⏳ {request['trip_date']}"
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=request['user_id'],
                text=f"✅ Ваша заявка на оклейку населенного пункта '{request['place_name']}' подтверждена!\n"
                     f"Дата поездки: {request['trip_date']}\n\n"
                     f"Спасибо за вашу активность! 🎉"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю: {e}")
        
        # Сообщаем в чат о подтверждении назначения
        await send_target_chat_message(
            context,
            f"✅ Подтверждено назначение: {request['place_name']} - {request['user_name']} ({request['trip_date']})"
        )
        
        # Удаляем заявку из очереди
        pending_requests[:] = [r for r in pending_requests if r['id'] != request_id]
        
        # Обновляем сообщение
        await query.edit_message_text(
            text=f"✅ Заявка подтверждена!\n"
                 f"Место: {request['place_name']}\n"
                 f"Пользователь: {request['user_name']}\n"
                 f"Дата: {request['trip_date']}"
        )
        
        # Уведомляем специальных пользователей
        await send_notification_to_special_users(
            context,
            f"✅ Заявка подтверждена пользователем {query.from_user.first_name}\n"
            f"Место: {request['place_name']}\n"
            f"Волонтер: {request['user_name']}"
        )
    
    elif data.startswith('reject_'):
        request_id = int(data.split('_')[1])
        request = next((r for r in pending_requests if r['id'] == request_id), None)
        
        if not request:
            await query.edit_message_text(text="❌ Заявка не найдена или уже обработана.")
            return
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=request['user_id'],
                text=f"❌ Ваша заявка на оклейку населенного пункта '{request['place_name']}' отклонена.\n"
                     f"Пожалуйста, свяжитесь с организаторами для выяснения причин."
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления пользователю: {e}")
        
        # Удаляем заявку из очереди
        pending_requests[:] = [r for r in pending_requests if r['id'] != request_id]
        
        # Обновляем сообщение
        await query.edit_message_text(
            text=f"❌ Заявка отклонена!\n"
                 f"Место: {request['place_name']}\n"
                 f"Пользователь: {request['user_name']}"
        )
        
        # Уведомляем специальных пользователей
        await send_notification_to_special_users(
            context,
            f"❌ Заявка отклонена пользователем {query.from_user.first_name}\n"
            f"Место: {request['place_name']}\n"
            f"Волонтер: {request['user_name']}"
        )

async def view_pending_request_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр деталей заявки"""
    query = update.callback_query
    await query.answer()
    
    # Обновляем активность пользователя
    await update_user_activity(query.from_user.id)
    
    request_id = int(query.data.split('_')[2])
    request = next((r for r in pending_requests if r['id'] == request_id), None)
    
    if not request:
        await query.edit_message_text(text="❌ Заявка не найдена.")
        return
    
    request_text = (
        f"📋 Детали заявки #{request_id}:\n"
        f"📍 Место: {request['place_name']}\n"
        f"👤 Пользователь: {request['user_name']}\n"
        f"📅 Дата поездки: {request['trip_date']}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{request_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{request_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text=request_text, reply_markup=reply_markup)

async def show_pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список заявок на подтверждение"""
    query = update.callback_query
    
    # Обновляем активность пользователя
    await update_user_activity(query.from_user.id)
    
    if not pending_requests:
        await query.edit_message_text(text="✅ Нет заявок, ожидающих подтверждения.")
        return
    
    requests_text = "⏳ Заявки, ожидающие подтверждения:\n\n"
    
    keyboard = []
    for request in pending_requests:
        request_text = (
            f"📍 {request['place_name']}\n"
            f"👤 {request['user_name']}\n"
            f"📅 {request['trip_date']}\n"
        )
        requests_text += f"#{request['id']} - {request['place_name']} ({request['user_name']})\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"📋 #{request['id']} - {request['place_name']}",
                callback_data=f"view_request_{request['id']}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=requests_text, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для диалогов"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Обновляем активность пользователя
    await update_user_activity(user_id)
    
    # Проверяем членство в группе для всех пользователей, кроме случаев когда пользователь уже в процессе диалога
    if user_id not in temp_data and not await is_user_in_target_chat(user_id, context):
        await send_private_message(
            update,
            context,
            f"❌ Для использования бота необходимо состоять в группе {TARGET_CHAT_ID}\n\n"
            f"Пожалуйста, присоединитесь к группе и попробуйте снова."
        )
        return
    
    # Сначала проверяем, не является ли сообщение координатами
    coordinates = extract_coordinates(text)
    if coordinates and user_id not in temp_data:
        # Если найдены координаты и пользователь не в процессе диалога с ботом
        lat, lon = coordinates
        yandex_map_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
        
        await update.message.reply_text(
            f"📍 Найдены координаты!\n"
            f"Широта: {lat}\n"
            f"Долгота: {lon}\n"
            f"Ссылка на Яндекс.Карты: {yandex_map_url}"
        )
        return
    
    if user_id not in temp_data:
        return
    
    # Удаляем сообщение пользователя только если он в процессе диалога
    asyncio.create_task(delete_message_after_delay(
        update.effective_chat.id, 
        update.message.message_id,
        context
    ))
    
    # ДОБАВЛЕНА ПРОВЕРКА: Убедимся, что все необходимые ключи присутствуют
    if 'process' not in temp_data[user_id] or 'step' not in temp_data[user_id]:
        await send_private_message(
            update,
            context,
            "❌ Ошибка в данных сессии. Пожалуйста, начните заново."
        )
        cleanup_user_data(user_id)
        return
    
    admin_processes = ['addplace', 'placeconf', 'placeplus', 'deleteplace']
    if temp_data[user_id].get('process') in admin_processes and not is_whitelisted(user_id):
        if 'last_message_id' in temp_data[user_id]:
            try:
                await delete_bot_message_safe(update, context, temp_data[user_id]['last_message_id'])
            except:
                pass
        
        await send_private_message(
            update,
            context,
            "❌ У вас нет прав для использования этой функции."
        )
        
        # Очищаем данные пользователя
        cleanup_user_data(user_id)
        return
    
    if 'last_message_id' in temp_data[user_id]:
        try:
            await delete_bot_message_safe(update, context, temp_data[user_id]['last_message_id'])
        except:
            pass
    
    current_process = temp_data[user_id]['process']
    current_step = temp_data[user_id]['step']
    
    if current_process == 'addplace':
        if current_step == 'name':
            names = []
            for line in text.split('\n'):
                for name in line.split(','):
                    clean_name = name.strip()
                    if clean_name:
                        names.append(clean_name)
            
            if not names:
                await send_private_message(
                    update,
                    context,
                    "❌ Не найдено названий населенных пунктов. Попробуйте еще раз."
                )
                return
            
            added_places = []
            for name in names:
                new_place = {
                    'name': name,
                    'completed': False,
                    'user': None,
                    'date': None,
                    'files': [],
                    'added_date': datetime.now().strftime("%d.%m.%Y"),
                    'pending': False
                }
                places.append(new_place)
                added_places.append(name)
            
            if len(added_places) == 1:
                announcement = f"📍 Добавлен новый населенный пункт для оклейки: {added_places[0]}"
            else:
                places_list = "\n".join([f"• {place}" for place in added_places])
                announcement = f"📍 Добавлены новые населенные пункты для оклейки ({len(added_places)}):\n{places_list}"
            
            await send_target_chat_message(context, announcement)
            
            # Очищаем данные пользователя
            cleanup_user_data(user_id)
    
    elif current_process == 'placeconf':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                temp_data[user_id]['place_index'] = places.index(sorted_places[place_number - 1])
                temp_data[user_id]['step'] = 'enter_user'
                
                await send_private_message(
                    update,
                    context,
                    "Введите телеграмм ник пользователя, который будет оклеивать:"
                )
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
        
        elif current_step == 'enter_user':
            temp_data[user_id]['user'] = text
            temp_data[user_id]['step'] = 'enter_date'
            
            await send_private_message(
                update,
                context,
                "Введите дату, когда нужно оклеить:"
            )
        
        elif current_step == 'enter_date':
            place_index = temp_data[user_id]['place_index']
            user_name = temp_data[user_id]['user']
            
            places[place_index]['user'] = user_name
            places[place_index]['date'] = f"⏳ {text}"
            
            await send_target_chat_message(
                context,
                f"✅ Назначение добавлено!\n"
                f"Населенный пункт: {places[place_index]['name']}\n"
                f"Ответственный: {user_name}\n"
                f"Дата: ⏳ {text}"
            )
            
            # Очищаем данные пользователя
            cleanup_user_data(user_id)
    
    elif current_process == 'placeplus':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                
                temp_data[user_id]['place_index'] = place_index
                temp_data[user_id]['step'] = 'enter_date'
                
                await send_private_message(
                    update,
                    context,
                    f"Введите дату оклейки населенного пункта '{places[place_index]['name']}':"
                )
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
        
        elif current_step == 'enter_date':
            temp_data[user_id]['completion_date'] = text
            temp_data[user_id]['step'] = 'enter_paster'
            
            await send_private_message(
                update,
                context,
                "Введите телеграмм ник пользователя, который оклеил:"
            )
        
        elif current_step == 'enter_paster':
            place_index = temp_data[user_id]['place_index']
            completion_date = temp_data[user_id]['completion_date']
            paster_name = text
            
            # Отмечаем как оклеенное
            places[place_index]['completed'] = True
            places[place_index]['completed_date'] = completion_date
            places[place_index]['completed_by'] = paster_name
            
            # Формируем сообщение для чата - только дата оклейки
            thank_you_text = f"✅ {places[place_index]['name']} ({completion_date})"
            
            try:
                await send_target_chat_message(context, thank_you_text)
                await send_private_message(update, context, "✅ Оклейка подтверждена и сообщение отправлено в чат!")
            except Exception as e:
                await send_private_message(update, context, "❌ Не удалось отправить сообщение в чат. Попробуйте еще раз.")
                return
            
            # Очищаем данные пользователя
            cleanup_user_data(user_id)
    
    elif current_process == 'placeplus_with_files':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                
                temp_data[user_id]['place_index'] = place_index
                temp_data[user_id]['step'] = 'enter_date'
                
                await send_private_message(
                    update,
                    context,
                    f"Введите дату оклейки населенного пункта '{places[place_index]['name']}':"
                )
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
        
        elif current_step == 'enter_date':
            temp_data[user_id]['completion_date'] = text
            temp_data[user_id]['step'] = 'enter_paster'
            
            await send_private_message(
                update,
                context,
                "Введите телеграмм ник пользователя, который оклеил:"
            )
        
        elif current_step == 'enter_paster':
            temp_data[user_id]['paster_name'] = text
            temp_data[user_id]['step'] = 'upload_files'
            
            # Для специальных пользователей устанавливаем увеличенный таймаут для загрузки файлов
            process_type = 'file_upload' if is_file_upload_user(user_id) else None
            
            await send_private_message(
                update,
                context,
                "Теперь загрузите файлы (фото, документы) для этого места. Вы можете загрузить несколько файлов. Когда закончите, напишите 'готово'.",
                process_type=process_type
            )
        
        elif current_step == 'upload_files':
            if text.lower() == 'готово':
                place_index = temp_data[user_id]['place_index']
                completion_date = temp_data[user_id]['completion_date']
                paster_name = temp_data[user_id]['paster_name']
                
                # Отмечаем как оклеенное
                places[place_index]['completed'] = True
                places[place_index]['completed_date'] = completion_date
                places[place_index]['completed_by'] = paster_name
                
                # Формируем сообщение для чата - только дата оклейки и количество файлов
                files_count = len(places[place_index].get('files', []))
                thank_you_text = f"✅ {places[place_index]['name']} ({completion_date}) 📎{files_count} файлов"
                
                try:
                    await send_target_chat_message(context, thank_you_text)
                    await send_private_message(update, context, f"✅ Оклейка подтверждена! Загружено {files_count} файлов. Сообщение отправлено в чат!")
                except Exception as e:
                    await send_private_message(update, context, "❌ Не удалось отправить сообщение в чат. Попробуйте еще раз.")
                    return
                
                # Очищаем данные пользователя
                cleanup_user_data(user_id)
    
    elif current_process == 'user_choose_place':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                
                temp_data[user_id]['place_index'] = place_index
                temp_data[user_id]['step'] = 'enter_date'
                
                await send_private_message(
                    update,
                    context,
                    f"Введите дату предполагаемой поездки для оклейки '{places[place_index]['name']}':"
                )
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
        
        elif current_step == 'enter_date':
            place_index = temp_data[user_id]['place_index']
            trip_date = text
            user = update.effective_user
            
            # Получаем информацию о пользователе
            user_name = user.first_name
            if user.username:
                user_name += f" (@{user.username})"
            
            # Создаем заявку на подтверждение
            request_id = len(pending_requests) + 1
            request = {
                'id': request_id,
                'place_index': place_index,
                'place_name': places[place_index]['name'],
                'user_id': user.id,
                'user_name': user_name,
                'trip_date': trip_date,
                'timestamp': datetime.now().strftime("%d.%m.%Y %H:%M")
            }
            pending_requests.append(request)
            
            # Отправляем уведомление специальным пользователям
            notification_text = (
                f"📍 Новая заявка на оклейку #{request_id}:\n"
                f"Населенный пункт: {places[place_index]['name']}\n"
                f"Пользователь: {user_name}\n"
                f"Дата предполагаемой поездки: {trip_date}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{request_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{request_id}")
                ],
                [
                    InlineKeyboardButton("📋 Подробнее", callback_data=f"view_request_{request_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await send_notification_to_special_users(context, notification_text, reply_markup)
            
            # Отправляем подтверждение пользователю
            await send_private_message(
                update,
                context,
                f"✅ Ваша заявка на оклейку населенного пункта '{places[place_index]['name']}' отправлена на подтверждение!\n"
                f"Дата поездки: {trip_date}\n\n"
                f"Ожидайте подтверждения от организаторов. Вы получите уведомление, когда заявка будет рассмотрена."
            )
            
            # Очищаем временные данные
            cleanup_user_data(user_id)
    
    elif current_process == 'cancel_responsible':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                place = places[place_index]
                
                # Сохраняем информацию о предыдущем ответственном для уведомления
                previous_user = place.get('user')
                previous_date = place.get('date')
                
                # Отменяем ответственного
                places[place_index]['user'] = None
                places[place_index]['date'] = None
                
                # Отправляем уведомление в чат
                await send_target_chat_message(
                    context,
                    f"❌ Ответственный отменен для населенного пункта '{place['name']}'\n"
                    f"Предыдущий ответственный: {previous_user}\n"
                    f"Предыдущая дата: {previous_date}"
                )
                
                # Подтверждаем пользователю
                await send_private_message(
                    update,
                    context,
                    f"✅ Ответственный отменен для населенного пункта '{place['name']}'!\n"
                    f"Предыдущий ответственный: {previous_user}\n"
                    f"Предыдущая дата: {previous_date}"
                )
                
                # Очищаем временные данные
                cleanup_user_data(user_id)
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
    
    elif current_process == 'view_files':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                place = places[place_index]
                
                # Показываем информацию о месте
                place_info = (
                    f"📋 Информация о населенном пункте:\n"
                    f"Название: {place['name']}\n"
                    f"Статус: {'✅ Оклеен' if place.get('completed') else '❌ Не оклеен'}\n"
                    f"Ответственный: {place.get('user', 'не назначен')}\n"
                    f"Дата: {place.get('date', 'не указана')}\n"
                )
                
                if place.get('completed'):
                    place_info += f"Дата оклейки: {place.get('completed_date', 'не указана')}\n"
                    place_info += f"Кто оклеил: {place.get('completed_by', 'не указано')}\n"
                
                await send_private_message(update, context, place_info)
                
                # Показываем загруженные файлы
                if place.get('files'):
                    await send_private_message(update, context, f"📎 Загружено {len(place['files'])} файлов:")
                    
                    # Отправляем каждый файл
                    for file_info in place['files']:
                        try:
                            if file_info['type'] == 'photo':
                                await context.bot.send_photo(
                                    chat_id=user_id,
                                    photo=file_info['file_id'],
                                    caption=file_info.get('caption', '')
                                )
                            elif file_info['type'] == 'document':
                                await context.bot.send_document(
                                    chat_id=user_id,
                                    document=file_info['file_id'],
                                    caption=file_info.get('caption', '')
                                )
                        except Exception as e:
                            print(f"Ошибка отправки файла: {e}")
                            await send_private_message(update, context, f"❌ Не удалось отправить файл: {file_info.get('caption', 'Без названия')}")
                else:
                    await send_private_message(update, context, "📎 Для этого места нет загруженных файлов.")
                
                # Очищаем временные данные
                cleanup_user_data(user_id)
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )
    
    elif current_process == 'deleteplace':
        if current_step == 'select_place':
            try:
                place_number = int(text)
                sorted_places = temp_data[user_id]['sorted_places']
                
                if place_number < 1 or place_number > len(sorted_places):
                    await send_private_message(
                        update,
                        context,
                        f"Неверный номер. Доступны номера от 1 до {len(sorted_places)}"
                    )
                    return
                
                place_index = places.index(sorted_places[place_number - 1])
                removed_place = places.pop(place_index)
                
                # Удаляем связанные заявки из очереди
                pending_requests[:] = [r for r in pending_requests if r['place_index'] != place_index]
                
                await send_target_chat_message(
                    context,
                    f"🗑️ Населенный пункт '{removed_place['name']}' удален из списка!"
                )
                
                # Очищаем данные пользователя
                cleanup_user_data(user_id)
                
            except ValueError:
                await send_private_message(
                    update,
                    context,
                    "Номер должен быть числом"
                )

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загрузки файлов"""
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    await update_user_activity(user_id)
    
    # Проверяем членство в группе
    if not await is_user_in_target_chat(user_id, context):
        return
    
    # Проверяем, является ли пользователь специальным пользователем для загрузки файлов
    if not is_file_upload_user(user_id):
        return
    
    # Проверяем, находится ли пользователь в процессе загрузки файлов
    if user_id not in temp_data or temp_data[user_id].get('process') != 'placeplus_with_files' or temp_data[user_id].get('step') != 'upload_files':
        return
    
    # Получаем информацию о файле
    file_id = None
    file_type = None
    caption = update.message.caption or ""
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_type = 'photo'
    elif update.message.document:
        file_id = update.message.document.file_id
        file_type = 'document'
    
    if file_id and file_type:
        place_index = temp_data[user_id]['place_index']
        
        # Инициализируем список файлов, если его нет
        if 'files' not in places[place_index]:
            places[place_index]['files'] = []
        
        # Добавляем информацию о файле
        places[place_index]['files'].append({
            'file_id': file_id,
            'type': file_type,
            'caption': caption,
            'uploaded_by': user_id,
            'upload_date': datetime.now().strftime("%d.%m.%Y %H:%M")
        })
        
        await send_private_message(
            update,
            context,
            f"✅ Файл загружен! Загружено файлов: {len(places[place_index]['files'])}\n"
            f"Продолжайте загружать файлы или напишите 'готово' для завершения.",
            process_type='file_upload'
        )
    
    # Удаляем сообщение с файлом только если пользователь в процессе диалога
    asyncio.create_task(delete_message_after_delay(
        update.effective_chat.id, 
        update.message.message_id,
        context
    ))

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
    user_id = update.effective_user.id
    text = update.message.text
    
    # Проверяем членство в группе
    if not await is_user_in_target_chat(user_id, context):
        return
    
    # Проверяем, находится ли пользователь в процессе диалога с ботом
    if user_id in temp_data:
        return
    
    # Извлекаем координаты из текста
    coordinates = extract_coordinates(text)
    if coordinates:
        lat, lon = coordinates
        yandex_map_url = f"https://yandex.ru/maps/?pt={lon},{lat}&z=17&l=map"
        
        await update.message.reply_text(
            f"📍 Найдены координаты!\n"
            f"Широта: {lat}\n"
            f"Долгота: {lon}\n"
            f"Ссылка на Яндекс.Карты: {yandex_map_url}"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    print(f"Произошла ошибка: {context.error}")
    # Можно добавить отправку сообщения об ошибке администратору

def main():
    """Запуск бота"""
    app = Application.builder().token(token).build()
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    app.add_handler(CommandHandler("privet_toc9", privet_toc9))
    app.add_handler(CommandHandler("s", s))
    app.add_handler(CommandHandler("p", p))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчики текстовых сообщений, файлов и координат
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_files))
    
    # Обработчик координат - должен быть после других обработчиков
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coordinates))
    
    print("Бот Мухтар запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()