#!/bin/bash
set -e  # Прерывать выполнение при ошибках

echo "Checking Python version..."
python3 --version

echo "Installing dependencies..."
pip3 install -r requirements.txt

echo "Starting bot..."
exec python3 test_bot.py