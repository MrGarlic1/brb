#!/bin/bash
SOURCE_DIR="$(dirname "$0")"
cd "$SOURCE_DIR"

if ! grep -q "$SOURCE_DIR" .env; then
    sed -i '/PARENT=/d' ./.env
    echo "PARENT="${SOURCE_DIR}"" >> .env
fi
if [ ! -d ./venv/bin ]; then
    python3 -m venv venv
    source ./venv/bin/activate
    pip install -r requirements.txt
fi

source ./venv/bin/activate
python main.py
