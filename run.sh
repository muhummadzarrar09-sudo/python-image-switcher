#!/bin/bash
# Run Image Switcher
pip install -r requirements.txt --quiet --break-system-packages
python src/app.py "$@"
