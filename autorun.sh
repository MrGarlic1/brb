#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d ./venv/bin ]; then
    python3 -m venv venv
    source ./venv/bin/activate
    pip install -r requirements.txt
fi
source ./venv/bin/activate
python main.py
