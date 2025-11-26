from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import re

# Токен бота
token = os.getenv('BOT_TOKEN', '8553241979:AAFPTPqcWs0f2EUoCSQI1vde_ZK9FakqfYM')

async def privet_toc9(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение бота"""
    welcome_text = """
🐕 Привет, я - Мухтар, для своих я просто Муха!

🏡 Я буду помогать с поисками моих друзей потеряшек, чтобы они скорее вернулись домой ✨

📚 Я пока только учусь и выполняю мало команд, но все впереди и я хотел бы расти вместе с группой и ее участниками

📍 Сейчас меня научили запоминать места где мы планируем или уже произвели оклейку местности, чтобы было понятно где и когда была произведена работа.
    """
    
    await update.message.reply_text(welcome_text)

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
    text = update.message.text
    
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

def main():
    """Запуск бота"""
    app = Application.builder().token(token).build()
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Оставляем только команду privet_toc9 и обработку координат
    app.add_handler(CommandHandler("privet_toc9", privet_toc9))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coordinates))
    
    print("Бот Мухтар запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()