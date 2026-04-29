#!/bin/bash
SOURCE_DIR="$(dirname "$0")"
SOURCE_DIR="$(readlink -e $SOURCE_DIR/../..)"
cd "$SOURCE_DIR"

if [ ! -f ./../.venv/bin/activate ]; then
    python3.13 -m venv ./.venv
    source ./.venv/bin/activate
    python3.13 -m pip install -r ./requirements.txt
fi

source ./.venv/bin/activate
python main.py
