"""
Zenith Launcher 1.1 - Minecraft launcher (PyQt6, liquid-glass UI)

Install:   pip install PyQt6 minecraft-launcher-lib requests
Run:       python zenith_launcher.py
Icon:      python zenith_launcher.py --make-icon
"""
import sys
import os
import re
import json
import uuid
import zlib
import math
import shutil
import random
import ctypes
import zipfile
import tempfile
import threading
import traceback
import subprocess
from pathlib import Path

import requests
import minecraft_launcher_lib as mll
from PyQt6.QtCore import (Qt, QObject, QPointF, QRectF, QSize, QTimer, QEvent, QUrl,
                          QVariantAnimation, QPropertyAnimation, QEasingCurve, pyqtSignal)
from PyQt6.QtGui import (QPixmap, QPainter, QColor, QPen, QBrush, QLinearGradient, QRadialGradient,
                         QIcon, QPolygonF, QPainterPath, QFont, QTextOption, QDesktopServices)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QAbstractButton, QButtonGroup, QStackedWidget, QFrame, QScrollArea,
                             QLineEdit, QComboBox, QListWidget, QListWidgetItem, QProgressBar, QSlider,
                             QSpinBox, QAbstractSpinBox, QFileDialog, QGraphicsOpacityEffect, QSizePolicy)

APP_NAME = "Zenith Launcher"
APP_VERSION = "1.4.0"
# Auto-update: put your public GitHub repo here, e.g. "yourname/zenith-launcher"
DEFAULT_UPDATE_REPO = "sryaddd/zenith-launcher"

HOME = Path.home() / ".zenith"
MC_DIR = HOME / "minecraft"
PROFILES_DIR = HOME / "profiles"
COVERS_DIR = HOME / "covers"
CACHE_DIR = HOME / "cache"
SETTINGS_FILE = HOME / "settings.json"
PROFILES_FILE = HOME / "profiles.json"
SERVERS_FILE = HOME / "servers.json"
LOG_FILE = HOME / "last_launch.log"
ERR_FILE = HOME / "error.log"
UA = {"User-Agent": f"ZenithLauncher/{APP_VERSION} (personal project)"}
MODRINTH = "https://api.modrinth.com/v2"
LOADERS = ["Vanilla", "Fabric", "Quilt", "Forge"]
NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

DEFAULT_SETTINGS = {
    "username": "Player", "memory": 3072, "width": 1280, "height": 720,
    "fullscreen": False, "jvm_args": "", "java_path": "",
    "theme": "Emerald", "glass": 55, "anim_bg": True, "smooth": True, "bg_image": "",
    "update_repo": DEFAULT_UPDATE_REPO, "auto_update": True,
}

THEMES = {
    "Emerald": dict(dark=True, bg0="#05080b", bg1="#0a1512", orbs=["#16a34a", "#0d9488", "#2563eb"],
                    accent="#22c55e", accent2="#4ade80", on_accent="#04200f"),
    "Ocean": dict(dark=True, bg0="#04070d", bg1="#0a1424", orbs=["#2563eb", "#06b6d4", "#6366f1"],
                  accent="#38bdf8", accent2="#7dd3fc", on_accent="#03202e"),
    "Sunset": dict(dark=True, bg0="#0b0608", bg1="#1a0e10", orbs=["#f97316", "#ec4899", "#a855f7"],
                   accent="#fb923c", accent2="#fdba74", on_accent="#2a1204"),
    "Violet": dict(dark=True, bg0="#07050e", bg1="#130d24", orbs=["#7c3aed", "#c026d3", "#2563eb"],
                   accent="#a78bfa", accent2="#c4b5fd", on_accent="#150b33"),
    "Rose": dict(dark=True, bg0="#0c0508", bg1="#1c0c14", orbs=["#e11d48", "#f472b6", "#fb7185"],
                 accent="#fb7185", accent2="#fda4af", on_accent="#3a0612"),
    "Midnight": dict(dark=True, bg0="#000000", bg1="#06070b", orbs=["#1e293b", "#312e81", "#0f172a"],
                     accent="#e2e8f0", accent2="#ffffff", on_accent="#0b0f19"),
    "Frost": dict(dark=False, bg0="#e8eef7", bg1="#d9e5f6", orbs=["#60a5fa", "#a78bfa", "#34d399"],
                  accent="#2563eb", accent2="#3b82f6", on_accent="#ffffff"),
}

IMG = None  # ImageLoader, created in main()


class _Theme:
    def __init__(self):
        self.smooth = True
        self.set("Emerald", 55)

    def set(self, name, glass):
        d = THEMES.get(name, THEMES["Emerald"])
        self.name = name if name in THEMES else "Emerald"
        self.dark = d["dark"]
        self.bg0, self.bg1 = QColor(d["bg0"]), QColor(d["bg1"])
        self.orbs = [QColor(c) for c in d["orbs"]]
        self.accent, self.accent2, self.on_accent = QColor(d["accent"]), QColor(d["accent2"]), QColor(d["on_accent"])
        self.glass = int(glass)
        self.text = QColor("#eef2f7") if self.dark else QColor("#0f172a")
