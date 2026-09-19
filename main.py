#!/usr/bin/env python3
"""
Launcher for Image Switcher - run this file to start the app
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    main()
