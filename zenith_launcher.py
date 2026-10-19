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
APP_VERSION = "1.4.1"
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
        self.sub = QColor("#9aa4b2") if self.dark else QColor("#475569")


THEME = _Theme()


# ------------------------------------------------------------------ helpers
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def total_ram_mb():
    try:
        if os.name == "nt":
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return int(m.ullTotalPhys / 1048576)
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1048576)
    except Exception:
        return 8192


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def download(url, dest, progress=None):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, headers=UA, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done, total)


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "profile"


def parse_version(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or "0")) or (0,)


def game_dir(p):
    return p["dir"] if p.get("isolated", True) else mll.utils.get_minecraft_directory()


def open_path(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def rgba(c, a):
    q = QColor(c)
    q.setAlpha(max(0, min(255, int(a))))
    return q


def mix(a, b, t):
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def css(c, a=None):
    q = QColor(c)
    if a is None:
        return q.name()
    return f"rgba({q.red()},{q.green()},{q.blue()},{int(a)})"


def run_anim(anim, start, end, ms, curve=QEasingCurve.Type.OutCubic):
    anim.stop()
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setDuration(max(1, ms if THEME.smooth else 1))
    anim.setEasingCurve(QEasingCurve(curve))
    anim.start()


def make_anim(owner, slot):
    a = QVariantAnimation(owner)
    a.valueChanged.connect(slot)
    return a


def draw_text(p, rect, text, align="center", color=None, font=None, elide=True):
    if font is not None:
        p.setFont(font)
    if color is not None:
        p.setPen(color)
    if elide:
        text = p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapMode.NoWrap)
    if align == "left":
        opt.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    elif align == "right":
        opt.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
    else:
        opt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    p.drawText(QRectF(rect), text, opt)


def lbl(text="", name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    if wrap:
        l.setWordWrap(True)
    return l


def call_safe(fn):
    try:
        fn()
    except RuntimeError:
        pass  # widget was deleted


# ------------------------------------------------------------------ stylesheet
def build_qss():
    t = THEME
    txt, sub = css(t.text), css(t.sub)
    solid = "#11151c" if t.dark else "#f4f7fc"
    border = css(QColor(255, 255, 255), 34) if t.dark else css(QColor(15, 23, 42), 40)
    field = css(QColor(255, 255, 255), 16) if t.dark else css(QColor(255, 255, 255), 175)
    hover = css(QColor(255, 255, 255), 14) if t.dark else css(QColor(15, 23, 42), 16)
    soft = css(t.accent, 60)
    handle = css(QColor(255, 255, 255), 55) if t.dark else css(QColor(15, 23, 42), 70)
    return f"""
* {{ outline: none; }}
QWidget {{ background: transparent; color: {txt}; font-family: 'Segoe UI Variable Text','Segoe UI','SF Pro Text','Helvetica Neue',Arial; font-size: 13px; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
QLabel#sub {{ color: {sub}; font-size: 12px; }}
QLabel#accent {{ color: {css(t.accent2 if t.dark else t.accent)}; font-weight: 600; }}
QLabel#err {{ color: #f87171; }}
QToolTip {{ background: {solid}; color: {txt}; border: 1px solid {border}; padding: 6px 9px; border-radius: 8px; }}
QLineEdit, QSpinBox {{ background: {field}; border: 1px solid {border}; border-radius: 13px; padding: 9px 13px; selection-background-color: {css(t.accent)}; selection-color: {css(t.on_accent)}; }}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {css(t.accent)}; }}
QComboBox {{ background: {field}; border: 1px solid {border}; border-radius: 13px; padding: 8px 13px; padding-right: 30px; }}
QComboBox:hover {{ border: 1px solid {css(t.accent)}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView, QComboBoxPrivateContainer {{ background: {solid}; border: 1px solid {border}; border-radius: 12px; selection-background-color: {soft}; selection-color: {txt}; padding: 4px; }}
QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 14px; margin: 2px 0; }}
QListWidget::item:hover {{ background: {hover}; }}
QListWidget::item:selected {{ background: {soft}; color: {txt}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {handle}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {css(t.accent, 160)}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0px; }}
QProgressBar {{ background: {field}; border: none; border-radius: 4px; min-height: 8px; max-height: 8px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {css(t.accent)}, stop:1 {css(t.accent2)}); border-radius: 4px; }}
QSlider::groove:horizontal {{ height: 6px; background: {field}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {css(t.accent)}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 1px solid rgba(0,0,0,70); width: 22px; height: 22px; margin: -9px 0; border-radius: 11px; }}
"""


# ------------------------------------------------------------------ vector icons
def draw_icon(name, p, r, col, width=1.8):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()

    def P(a, b):
        return QPointF(x + a * w, y + b * h)

    def poly(*pts, close=False):
        path = QPainterPath()
        path.moveTo(P(*pts[0]))
        for q in pts[1:]:
            path.lineTo(P(*q))
        if close:
            path.closeSubpath()
        p.drawPath(path)

    def rect(a, b, c, d, rad=2):
        p.drawRoundedRect(QRectF(x + a * w, y + b * h, c * w, d * h), rad, rad)

    def ell(a, b, c, d):
        p.drawEllipse(QRectF(x + a * w, y + b * h, c * w, d * h))

    def dot(a, b, rr):
        p.setBrush(col)
        p.drawEllipse(P(a, b), rr, rr)
        p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "home":
        poly((.1, .5), (.5, .12), (.9, .5))
        poly((.2, .44), (.2, .88), (.8, .88), (.8, .44))
        poly((.42, .88), (.42, .62), (.58, .62), (.58, .88))
    elif name == "versions":
        for i in (0, 1):
            for j in (0, 1):
                rect(.1 + i * .44, .1 + j * .44, .36, .36, 4)
    elif name == "mods":
        poly((.5, .08), (.88, .3), (.88, .7), (.5, .92), (.12, .7), (.12, .3), close=True)
        poly((.12, .3), (.5, .52), (.88, .3))
        poly((.5, .52), (.5, .92))
    elif name == "servers":
        ell(.1, .1, .8, .8)
        ell(.33, .1, .34, .8)
        poly((.1, .5), (.9, .5))
    elif name == "theme":
        ell(.1, .1, .8, .8)
        dot(.34, .4, w * .06)
        dot(.55, .3, w * .06)
        dot(.68, .52, w * .06)
    elif name == "settings":
        poly((.12, .25), (.88, .25))
        poly((.12, .5), (.88, .5))
        poly((.12, .75), (.88, .75))
        dot(.65, .25, w * .1)
        dot(.34, .5, w * .1)
        dot(.72, .75, w * .1)
    elif name == "plus":
        poly((.5, .15), (.5, .85))
        poly((.15, .5), (.85, .5))
    elif name == "update":
        p.drawArc(QRectF(x + .15 * w, y + .15 * h, .7 * w, .7 * h), 40 * 16, 280 * 16)
        poly((.85, .12), (.85, .36), (.62, .36))
    elif name == "check":
        poly((.18, .52), (.42, .76), (.84, .26))
    elif name == "trash":
        poly((.18, .27), (.82, .27))
        poly((.38, .27), (.4, .13), (.6, .13), (.62, .27))
        poly((.27, .27), (.32, .88), (.68, .88), (.73, .27))
        poly((.45, .45), (.45, .72))
        poly((.55, .45), (.55, .72))
    elif name == "play":
        p.setBrush(col)
        poly((.3, .18), (.82, .5), (.3, .82), close=True)
    elif name == "user":
        ell(.3, .1, .4, .4)
        poly((.14, .9), (.17, .72), (.34, .58), (.66, .58), (.83, .72), (.86, .9))
    elif name == "image":
        rect(.1, .15, .8, .7, 4)
        dot(.32, .38, w * .06)
        poly((.12, .78), (.4, .52), (.58, .7), (.72, .58), (.9, .78))
    elif name == "close":
        poly((.22, .22), (.78, .78))
        poly((.78, .22), (.22, .78))
    elif name == "wand":
        poly((.16, .86), (.6, .42))
        poly((.75, .1), (.75, .42))
        poly((.59, .26), (.91, .26))
        poly((.2, .22), (.2, .36))
        poly((.13, .29), (.27, .29))
    elif name == "download":
        poly((.5, .12), (.5, .62))
        poly((.3, .45), (.5, .66), (.7, .45))
        poly((.15, .86), (.85, .86))
    elif name == "folder":
        poly((.1, .24), (.4, .24), (.48, .35), (.9, .35), (.9, .8), (.1, .8), close=True)
    elif name == "swap":
        poly((.15, .34), (.85, .34))
        poly((.68, .17), (.87, .34), (.68, .51))
        poly((.85, .7), (.15, .7))
        poly((.32, .53), (.13, .7), (.32, .87))
    elif name == "save":
        rect(.14, .14, .72, .72, 4)
        poly((.3, .14), (.3, .4), (.7, .4), (.7, .14))
        rect(.3, .58, .4, .28, 2)
    elif name == "search":
        ell(.12, .12, .55, .55)
        poly((.6, .6), (.88, .88))
    p.restore()


# ------------------------------------------------------------------ glass painting
def paint_glass(p, r, radius, tint=None, hover=0.0, strength=1.0):
    dark = THEME.dark
    g = THEME.glass
    base = (13 + g * 0.30) if dark else (95 + g * 0.95)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.fillPath(path, QColor(255, 255, 255, int((base + hover * 20) * strength)))
    if tint is not None:
        p.fillPath(path, rgba(tint, 46 + hover * 26))
    sheen = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() * 0.6))
    sheen.setColorAt(0, QColor(255, 255, 255, 64 if dark else 150))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillPath(path, QBrush(sheen))
    bg = QLinearGradient(r.topLeft(), r.bottomRight())
    bg.setColorAt(0, QColor(255, 255, 255, 96 if dark else 235))
    bg.setColorAt(1, QColor(255, 255, 255, 16 if dark else 90))
    p.setPen(QPen(QBrush(bg), 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


# ------------------------------------------------------------------ generated artwork (own art, no game assets)
_ART_CACHE = {}


def make_art(key, w, h, hue=None):
    ck = (key, w, h, hue)
    if ck in _ART_CACHE:
        return _ART_CACHE[ck]
    rnd = random.Random(zlib.crc32(key.encode()))
    if hue is None:
        hue = rnd.randrange(360)
    night = rnd.random() < 0.45
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sky = QLinearGradient(0, 0, 0, h)
    if night:
        sky.setColorAt(0, QColor.fromHsl(hue, 150, 22))
        sky.setColorAt(0.7, QColor.fromHsl((hue + 25) % 360, 150, 60))
        sky.setColorAt(1, QColor.fromHsl((hue + 45) % 360, 170, 110))
    else:
        sky.setColorAt(0, QColor.fromHsl(hue, 170, 95))
        sky.setColorAt(0.65, QColor.fromHsl((hue + 30) % 360, 190, 150))
        sky.setColorAt(1, QColor.fromHsl((hue + 55) % 360, 200, 195))
    p.fillRect(0, 0, w, h, sky)
    p.setPen(Qt.PenStyle.NoPen)
    if night:
        for _ in range(int(w * h / 1800) + 12):
            s = rnd.random() * 1.6 + 0.5
            p.setBrush(QColor(255, 255, 255, rnd.randint(90, 230)))
            p.drawEllipse(QPointF(rnd.random() * w, rnd.random() * h * 0.55), s, s)
    cx, cy, rr = w * rnd.uniform(0.25, 0.75), h * rnd.uniform(0.2, 0.34), w * 0.075
    glow = QRadialGradient(QPointF(cx, cy), rr * 3.2)
    glow.setColorAt(0, QColor(255, 244, 200, 150))
    glow.setColorAt(1, QColor(255, 244, 200, 0))
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(cx, cy), rr * 3.2, rr * 3.2)
    p.setBrush(QColor(255, 247, 214) if not night else QColor(238, 244, 255))
    p.drawEllipse(QPointF(cx, cy), rr, rr)
    for layer in range(3):
        base = h * (0.5 + layer * 0.11)
        col = QColor.fromHsl((hue + 18 * layer + 200) % 360, 110, max(28, 92 - layer * 24))
        pts = [QPointF(0, h), QPointF(0, base)]
        steps = 7
        for i in range(1, steps + 1):
            pts.append(QPointF(w * i / steps, base - rnd.uniform(0.03, 0.2 - layer * 0.04) * h))
        pts.append(QPointF(w, h))
        p.setBrush(col)
        p.drawPolygon(QPolygonF(pts))
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    b = max(6, w // 20)
    top_y = int(h * 0.8)
    for i, x in enumerate(range(0, w + b, b)):
        off = rnd.randint(-1, 1) * b
        gy = top_y + off
        p.setBrush(QColor.fromHsl(105 + rnd.randint(-8, 8), 150, 82 + rnd.randint(-8, 8)))
        p.drawRect(x, gy, b, b)
        yy = gy + b
        row = 0
        while yy < h:
            p.setBrush(QColor.fromHsl(28 + rnd.randint(-4, 4), 90, max(36, 74 - row * 9) + rnd.randint(-5, 5)))
            p.drawRect(x, yy, b, b)
            yy += b
            row += 1
    for _ in range(3):
        s = b * rnd.randint(1, 2)
        fx, fy = rnd.randint(8, max(9, w - s - 8)), rnd.randint(int(h * 0.2), int(h * 0.5))
        c = QColor.fromHsl((hue + rnd.randint(60, 200)) % 360, 180, 140)
        p.setBrush(c)
        p.drawRect(fx, fy, s, s)
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawRect(fx, fy, s, max(2, s // 4))
    p.end()
    _ART_CACHE[ck] = pm
    return pm


def get_cover(vid, w, h):
    for ext in ("png", "jpg", "jpeg", "webp"):
        f = COVERS_DIR / f"{vid}.{ext}"
        if f.exists():
            pm = QPixmap(str(f))
            if not pm.isNull():
                return pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
    return make_art(vid, w, h)


def make_logo(size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    g = QLinearGradient(0, 0, 0, s)
    g.setColorAt(0, THEME.accent2)
    g.setColorAt(1, THEME.accent)
    hexa = QPolygonF([QPointF(s * .5, s * .04), QPointF(s * .92, s * .27), QPointF(s * .92, s * .73),
                      QPointF(s * .5, s * .96), QPointF(s * .08, s * .73), QPointF(s * .08, s * .27)])
    p.setPen(QPen(QBrush(g), s * .07))
    p.setBrush(QColor(12, 18, 16))
    p.drawPolygon(hexa)
    p.setPen(QPen(QBrush(g), s * .09, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(s * .3, s * .64), QPointF(s * .5, s * .42), QPointF(s * .7, s * .64)]))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(s * .5, s * .27), s * .05, s * .05)
    p.end()
    return pm


def rounded_pix(pix, w, h, radius):
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(path)
    sp = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap((w - sp.width()) // 2, (h - sp.height()) // 2, sp)
    p.end()
    return out


def letter_avatar(text, size, radius=None):
    radius = size * 0.28 if radius is None else radius
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    hue = zlib.crc32(text.encode()) % 360
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor.fromHsl(hue, 170, 120))
    g.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 180, 80))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.fillPath(path, QBrush(g))
    f = QFont()
    f.setPixelSize(int(size * 0.46))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    draw_text(p, QRectF(0, 0, size, size), (text[:1] or "?").upper(), "center")
    p.end()
    return pm


class ImageLoader(QObject):
    loaded = pyqtSignal(str, bytes)

    def __init__(self):
        super().__init__()
        self.dir = CACHE_DIR / "img"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.waiting = {}
        self.loaded.connect(self._on_loaded)

    def _path(self, url):
        return self.dir / f"{zlib.crc32(url.encode()):08x}.img"

    def request(self, url, cb):
        if not url:
            return
        f = self._path(url)
        if f.exists():
            pm = QPixmap()
            if pm.loadFromData(f.read_bytes()):
                call_safe(lambda: cb(pm))
                return
        first = url not in self.waiting
        self.waiting.setdefault(url, []).append(cb)
        if first:
            threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url):
        try:
            r = requests.get(url, headers=UA, timeout=15)
            r.raise_for_status()
            self._path(url).write_bytes(r.content)
            self.loaded.emit(url, r.content)
        except Exception:
            self.loaded.emit(url, b"")

    def _on_loaded(self, url, data):
        cbs = self.waiting.pop(url, [])
        if not data:
            return
        pm = QPixmap()
        if pm.loadFromData(data):
            for cb in cbs:
                call_safe(lambda cb=cb: cb(pm))


# ------------------------------------------------------------------ glass widgets
class Background(QWidget):
    def __init__(self):
        super().__init__()
        self.t = 0.0
        self.animate = True
        self.img = None
        self._scaled = None
        self._scaled_size = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(45)

    def tick(self):
        if self.animate and not self.img and self.isVisible() and not self.window().isMinimized():
            self.t += 0.045
            self.update()

    def set_image(self, path):
        pm = QPixmap(path) if path and Path(path).exists() else None
        self.img = pm if pm is not None and not pm.isNull() else None
        self._scaled = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, THEME.bg0)
        g.setColorAt(1, THEME.bg1)
        p.fillRect(self.rect(), g)
        if self.img is not None:
            if self._scaled is None or self._scaled_size != (w, h):
                self._scaled = self.img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                               Qt.TransformationMode.SmoothTransformation)
                self._scaled_size = (w, h)
            p.drawPixmap((w - self._scaled.width()) // 2, (h - self._scaled.height()) // 2, self._scaled)
            p.fillRect(self.rect(), QColor(5, 8, 12, 150) if THEME.dark else QColor(240, 244, 250, 120))
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(THEME.orbs):
            ang = self.t * (0.35 + i * 0.17) + i * 2.1
            cx = w * (0.5 + 0.38 * math.cos(ang))
            cy = h * (0.5 + 0.34 * math.sin(ang * 1.3 + i))
            r = max(w, h) * (0.36 + 0.05 * i)
            rg = QRadialGradient(QPointF(cx, cy), r)
            rg.setColorAt(0, rgba(c, 120 if THEME.dark else 150))
            rg.setColorAt(1, rgba(c, 0))
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(cx, cy), r, r)


class Glass(QFrame):
    def __init__(self, radius=22, tint=None, parent=None, solid=False):
        super().__init__(parent)
        self.radius = radius
        self.tint = tint
        self.solid = solid

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        if self.solid:
            path = QPainterPath()
            path.addRoundedRect(r, self.radius, self.radius)
            p.fillPath(path, QColor(18, 22, 31, 246) if THEME.dark else QColor(244, 247, 252, 248))
        paint_glass(p, r, self.radius, self.tint)


class Divider(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(1)

    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor(255, 255, 255, 26) if THEME.dark else QColor(15, 23, 42, 30))


class GlassButton(QAbstractButton):
    """Liquid glass button: hover glow, press squish, ripple."""

    def __init__(self, text="", kind="normal", icon=None, height=40, align="center", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.kind, self.icon_name, self.align, self.sub = kind, icon, align, ""
        self._h = height
        self._hov = self._press = 0.0
        self._rip = 1.0
        self._rip_pt = QPointF(0, 0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ah = make_anim(self, self._set_hov)
        self._ap = make_anim(self, self._set_press)
        self._ar = make_anim(self, self._set_rip)

    def _set_hov(self, v):
        self._hov = v
        self.update()

    def _set_press(self, v):
        self._press = v
        self.update()

    def _set_rip(self, v):
        self._rip = v
        self.update()

    def setSub(self, s):
        self.sub = s
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(self.text().split("\n")[0]) + 38 + (26 if self.icon_name and self.text() else 0)
        if self.icon_name and not self.text():
            w = self._h
        return QSize(max(w, 44), self._h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 180)
        super().enterEvent(e)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 280)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._rip_pt = e.position()
        run_anim(self._ap, self._press, 1, 90)
        run_anim(self._ar, 0, 1, 560)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._ap, self._press, 0, 420, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        if not self.isEnabled():
            p.setOpacity(0.45)
        s = 1 - 0.06 * self._press
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        r = QRectF(1.5, 1.5, w - 3, h - 3)
        rad = min(h / 2, 26)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        T = THEME
        checked = self.isCheckable() and self.isChecked()
        if self.kind == "accent":
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, T.accent2.lighter(100 + int(self._hov * 12)))
            g.setColorAt(1, T.accent)
            p.fillPath(path, QBrush(g))
            gl = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + r.height() * .55))
            gl.setColorAt(0, QColor(255, 255, 255, 95))
            gl.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(path, QBrush(gl))
            p.setPen(QPen(QColor(255, 255, 255, 110), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            fg = T.on_accent
        else:
            tint = None
            fg = T.text
            if self.kind == "danger":
                tint, fg = QColor("#ef4444"), QColor("#f87171") if T.dark else QColor("#dc2626")
            elif checked:
                tint, fg = T.accent, (T.accent2 if T.dark else T.accent)
            if self.kind == "ghost" and not checked and self.kind != "danger":
                if self._hov > 0.01:
                    p.fillPath(path, QColor(255, 255, 255, int(30 * self._hov)) if T.dark
                               else QColor(15, 23, 42, int(22 * self._hov)))
            else:
                paint_glass(p, r, rad, tint, self._hov)
        if self._rip < 1:
            p.save()
            p.setClipPath(path)
            rr = self._rip * max(w, h) * 1.1
            rg = QRadialGradient(self._rip_pt, rr)
            rg.setColorAt(0, QColor(255, 255, 255, int(120 * (1 - self._rip))))
            rg.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(self._rip_pt, rr, rr)
            p.restore()
        txt = self.text()
        big = bool(self.sub)
        f = QFont(self.font())
        f.setPixelSize(22 if big else 14)
        f.setWeight(QFont.Weight.DemiBold if not big else QFont.Weight.Bold)
        p.setFont(f)
        fm = p.fontMetrics()
        ic = 18 if self.icon_name else 0
        gap = 8 if (ic and txt) else 0
        tw = fm.horizontalAdvance(txt)
        if self.align == "left":
            x0 = 18.0
        else:
            x0 = (w - (tw + ic + gap)) / 2
        if ic:
            ir = QRectF(x0, (h - ic) / 2, ic, ic)
            draw_icon(self.icon_name, p, ir, fg)
        if txt:
            if big:
                draw_text(p, QRectF(0, h * 0.14, w, h * 0.45), txt, "center", fg, f, False)
                f2 = QFont(self.font())
                f2.setPixelSize(12)
                draw_text(p, QRectF(0, h * 0.55, w, h * 0.3), self.sub, "center", rgba(fg, 200), f2)
            else:
                draw_text(p, QRectF(x0 + ic + gap, 0, w - x0 - ic - gap - 6, h), txt, "left", fg, f)


class Switch(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(54, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pos = 1.0 if checked else 0.0
        self._grow = 0.0
        self._a = make_anim(self, self._set_pos)
        self._g = make_anim(self, self._set_grow)
        self.toggled.connect(lambda c: run_anim(self._a, self._pos, 1.0 if c else 0.0, 380, QEasingCurve.Type.OutBack))

    def _set_pos(self, v):
        self._pos = v
        self.update()

    def _set_grow(self, v):
        self._grow = v
        self.update()

    def mousePressEvent(self, e):
        run_anim(self._g, self._grow, 1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._g, self._grow, 0, 260)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pos = max(0.0, min(1.0, self._pos))
        off = QColor(255, 255, 255, 46) if THEME.dark else QColor(15, 23, 42, 50)
        track = mix(off, THEME.accent, pos)
        tr = QRectF(1, 3, w - 2, h - 6)
        path = QPainterPath()
        path.addRoundedRect(tr, tr.height() / 2, tr.height() / 2)
        p.fillPath(path, track)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        kw = 24 + 8 * self._grow
        kx = 4 + self._pos * (w - 8 - kw)
        kr = QRectF(kx, (h - 24) / 2, kw, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(kr.translated(0, 1.5), 12, 12)
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(kr, 12, 12)


class NavButton(QAbstractButton):
    def __init__(self, icon, label):
        super().__init__()
        self.icon_name = icon
        self.setText(label)
        self.setCheckable(True)
        self.setFixedSize(66, 62)
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sel = self._hov = self._press = 0.0
        self._as = make_anim(self, lambda v: self._set("_sel", v))
        self._ah = make_anim(self, lambda v: self._set("_hov", v))
        self._ap = make_anim(self, lambda v: self._set("_press", v))
        self.toggled.connect(lambda c: run_anim(self._as, self._sel, 1.0 if c else 0.0, 420, QEasingCurve.Type.OutBack))

    def _set(self, name, v):
        setattr(self, name, v)
        self.update()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 160)
        super().enterEvent(e)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 240)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        run_anim(self._ap, self._press, 1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._ap, self._press, 0, 420, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        s = 1 - 0.08 * self._press
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        r = QRectF(3, 2, w - 6, h - 4)
        if self._hov > 0.01:
            path = QPainterPath()
            path.addRoundedRect(r, 20, 20)
            p.fillPath(path, QColor(255, 255, 255, int(24 * self._hov)) if THEME.dark else QColor(15, 23, 42, int(20 * self._hov)))
        sel = max(0.0, min(1.0, self._sel))
        if sel > 0.01:
            p.setOpacity(sel)
            paint_glass(p, r, 20, THEME.accent)
            p.setOpacity(1)
        col = mix(THEME.sub, THEME.accent2 if THEME.dark else THEME.accent, sel)
        if self._hov > 0 and sel < 1:
            col = mix(col, THEME.text, self._hov * 0.6 * (1 - sel))
        lift = -2 * sel
        draw_icon(self.icon_name, p, QRectF(w / 2 - 12, 9 + lift, 24, 24), col, 1.9)
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.DemiBold)
        draw_text(p, QRectF(0, 37 + lift, w, 16), self.text(), "center", col, f)


class FadeStack(QStackedWidget):
    def go(self, i):
        if i == self.currentIndex():
            return
        self.setCurrentIndex(i)
        if not THEME.smooth:
            return
        w = self.widget(i)
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", w)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        a.finished.connect(lambda: call_safe(lambda: w.setGraphicsEffect(None)))
        a.start()
        self._a = a


class Overlay(QWidget):
    """In-app modal (replaces pop-up windows)."""

    def __init__(self, host, card, width=560):
        super().__init__(host)
        self.host, self.card, self.cw = host, card, width
        card.setParent(self)
        self._p = 0.0
        self._closing = False
        self.setGeometry(host.rect())
        host.installEventFilter(self)
        self.anim = make_anim(self, self._tick)
        self.anim.finished.connect(self._finished)
        self.layout_card()
        self.show()
        self.raise_()
        self.setFocus()
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.eff.setOpacity(0.0)
        run_anim(self.anim, 0, 1, 320, QEasingCurve.Type.OutCubic)

    def layout_card(self):
        w = max(320, min(self.cw, self.width() - 40))
        self.card.setFixedWidth(w)
        lay = self.card.layout()
        lay.activate()
        h = max(self.card.sizeHint().height(), self.card.minimumSizeHint().height())
        if lay.hasHeightForWidth():
            h = max(h, lay.totalHeightForWidth(w))
        h = min(h, self.height() - 40)
        x = (self.width() - w) // 2
        y = (self.height() - h) // 2 + int((1 - self._p) * 28)
        self.card.setGeometry(x, y, w, h)

    def relayout(self):
        self.layout_card()

    def _tick(self, v):
        self._p = v if not self._closing else 1 - v
        if self.graphicsEffect() is not None:
            self.eff.setOpacity(max(0.0, min(1.0, self._p)))
        self.layout_card()
        self.update()

    def _finished(self):
        if self._closing:
            self.host.removeEventFilter(self)
            self.deleteLater()
        else:
            self._p = 1.0
            self.setGraphicsEffect(None)
            self.layout_card()

    def close_overlay(self, immediate=False):
        if self._closing:
            return
        self._closing = True
        if immediate or not THEME.smooth:
            self.host.removeEventFilter(self)
            self.hide()
            self.deleteLater()
            return
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        run_anim(self.anim, 0, 1, 220, QEasingCurve.Type.InCubic)

    def eventFilter(self, o, e):
        if o is self.host and e.type() == QEvent.Type.Resize:
            self.setGeometry(self.host.rect())
            self.layout_card()
        return False

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 150) if THEME.dark else QColor(20, 30, 50, 110))

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_overlay()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_overlay()


class Toast(Glass):
    def __init__(self, host):
        super().__init__(20, parent=host, solid=True)
        self.host = host
        self.label = QLabel("")
        self.label.setObjectName("h2")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 12, 22, 12)
        lay.addWidget(self.label)
        self.eff = QGraphicsOpacityEffect(self)
        self.eff.setOpacity(0)
        self.setGraphicsEffect(self.eff)
        self.hide()
        self._p = 0.0
        self.anim = make_anim(self, self._tick)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        host.installEventFilter(self)

    def eventFilter(self, o, e):
        if o is self.host and e.type() == QEvent.Type.Resize:
            self.place()
        return False

    def place(self):
        self.adjustSize()
        x = (self.host.width() - self.width()) // 2
        y = self.host.height() - 96 + int((1 - self._p) * 24)
        self.move(x, y)

    def _tick(self, v):
        self._p = v
        self.eff.setOpacity(max(0.0, min(1.0, v)))
        self.place()
        if v <= 0.01 and self.anim.endValue() == 0.0:
            self.hide()

    def show_msg(self, text, kind="ok"):
        self.label.setText(("✓  " if kind == "ok" else "!  ") + text)
        self.tint = QColor("#22c55e") if kind == "ok" else QColor("#ef4444")
        self.show()
        self.raise_()
        self.place()
        run_anim(self.anim, self._p, 1, 380, QEasingCurve.Type.OutBack)
        self.timer.start(2800 if kind == "ok" else 4200)

    def dismiss(self):
        run_anim(self.anim, self._p, 0, 260, QEasingCurve.Type.InCubic)


CARD_W, CARD_H = 168, 214


class VersionCard(QAbstractButton):
    def __init__(self, vid, vtype):
        super().__init__()
        self.vid, self.vtype = vid, vtype
        self.setCheckable(True)
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.art = get_cover(vid, CARD_W, CARD_H)
        self._hov = self._press = 0.0
        self._ah = make_anim(self, lambda v: self._set("_hov", v))
        self._ap = make_anim(self, lambda v: self._set("_press", v))

    def _set(self, n, v):
        setattr(self, n, v)
        self.update()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 220, QEasingCurve.Type.OutBack)
        super().enterEvent(e)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 260)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        run_anim(self._ap, self._press, 1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._ap, self._press, 0, 420, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        s = 0.94 + 0.04 * self._hov - 0.05 * self._press
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(3, 3, w - 6, h - 6), 20, 20)
        p.save()
        p.setClipPath(path)
        p.drawPixmap(3, 3, self.art)
        g = QLinearGradient(0, h * .5, 0, h)
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0, 185))
        p.fillRect(0, 0, w, h, QBrush(g))
        sh = QLinearGradient(0, 0, 0, h * .4)
        sh.setColorAt(0, QColor(255, 255, 255, 50))
        sh.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, w, int(h * .4), QBrush(sh))
        p.restore()
        f = QFont(self.font())
        f.setPixelSize(22)
        f.setBold(True)
        draw_text(p, QRectF(16, h - 58, w - 32, 28), self.vid, "left", QColor(255, 255, 255), f)
        f2 = QFont(self.font())
        f2.setPixelSize(11)
        f2.setWeight(QFont.Weight.DemiBold)
        draw_text(p, QRectF(16, h - 32, w - 32, 18), self.vtype.replace("_", " ").upper(), "left", QColor(255, 255, 255, 190), f2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.isChecked():
            p.setPen(QPen(THEME.accent, 3))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.drawPath(path)


class NewsCard(QWidget):
    def __init__(self, title, sub, key):
        super().__init__()
        self.title, self.sub = title, sub
        self.setFixedHeight(132)
        self.art = make_art(key, 520, 132)
        self._hov = 0.0
        self._ah = make_anim(self, self._set)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def _set(self, v):
        self._hov = v
        self.update()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 200)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 260)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(.5, .5, w - 1, h - 1), 20, 20)
        p.setClipPath(path)
        sc = self.art.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(int((w - sc.width()) / 2), int((h - sc.height()) / 2), sc)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(0, 0, 0, 20))
        g.setColorAt(1, QColor(0, 0, 0, int(170 - 30 * self._hov)))
        p.fillRect(self.rect(), QBrush(g))
        p.setClipping(False)
        f = QFont(self.font())
        f.setPixelSize(17)
        f.setBold(True)
        draw_text(p, QRectF(16, h - 52, w - 32, 24), self.title, "left", QColor(255, 255, 255), f)
        f2 = QFont(self.font())
        f2.setPixelSize(12)
        draw_text(p, QRectF(16, h - 30, w - 32, 20), self.sub, "left", QColor(255, 255, 255, 215), f2)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class Hero(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(250)
        self._sc = None
        self._sc_size = None
        self.refresh()

    def refresh(self):
        self.art = make_art(f"hero-{THEME.name}", 1000, 340, hue=THEME.accent.hue())
        self._sc = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(.5, .5, w - 1, h - 1), 28, 28)
        p.setClipPath(path)
        if self._sc is None or self._sc_size != (w, h):
            self._sc = self.art.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self._sc_size = (w, h)
        p.drawPixmap((w - self._sc.width()) // 2, (h - self._sc.height()) // 2, self._sc)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(0, 0, 0, 30))
        g.setColorAt(1, QColor(0, 0, 0, 120))
        p.fillRect(self.rect(), QBrush(g))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


class ThemeCard(QAbstractButton):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.setCheckable(True)
        self.setFixedSize(190, 118)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hov = self._press = 0.0
        self._ah = make_anim(self, lambda v: self._set("_hov", v))
        self._ap = make_anim(self, lambda v: self._set("_press", v))

    def _set(self, n, v):
        setattr(self, n, v)
        self.update()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 200, QEasingCurve.Type.OutBack)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 260)

    def mousePressEvent(self, e):
        run_anim(self._ap, self._press, 1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._ap, self._press, 0, 420, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        d = THEMES[self.name]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        s = 0.96 + 0.03 * self._hov - 0.04 * self._press
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(3, 3, w - 6, h - 6), 22, 22)
        p.setClipPath(path)
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor(d["bg0"]))
        g.setColorAt(1, QColor(d["bg1"]))
        p.fillRect(self.rect(), QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(d["orbs"]):
            cx, cy, r = w * (0.2 + 0.3 * i), h * (0.3 + 0.25 * (i % 2)), w * 0.55
            rg = QRadialGradient(QPointF(cx, cy), r)
            rg.setColorAt(0, rgba(QColor(c), 150))
            rg.setColorAt(1, rgba(QColor(c), 0))
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(cx, cy), r, r)
        glass = QRectF(14, h - 52, w - 28, 34)
        gp = QPainterPath()
        gp.addRoundedRect(glass, 17, 17)
        p.fillPath(gp, QColor(255, 255, 255, 60 if d["dark"] else 150))
        p.setBrush(QColor(d["accent"]))
        p.drawEllipse(QPointF(glass.left() + 17, glass.center().y()), 7, 7)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        draw_text(p, QRectF(glass.left() + 32, glass.top(), glass.width() - 40, glass.height()), self.name, "left",
                  QColor("#ffffff") if d["dark"] else QColor("#0f172a"), f)
        p.setClipping(False)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(d["accent"]) if self.isChecked() else QColor(255, 255, 255, 70), 3 if self.isChecked() else 1))
        p.drawPath(path)
        if self.isChecked():
            p.setBrush(QColor(d["accent"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(w - 22, 22), 12, 12)
            draw_icon("check", p, QRectF(w - 29, 15, 14, 14), QColor(d["on_accent"]), 2.2)


class OptionCard(QAbstractButton):
    def __init__(self, icon, title, desc):
        super().__init__()
        self.icon_name, self.title, self.desc = icon, title, desc
        self.setMinimumHeight(128)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hov = self._press = 0.0
        self._ah = make_anim(self, lambda v: self._set("_hov", v))
        self._ap = make_anim(self, lambda v: self._set("_press", v))

    def sizeHint(self):
        return QSize(220, 132)

    def _set(self, n, v):
        setattr(self, n, v)
        self.update()

    def enterEvent(self, e):
        run_anim(self._ah, self._hov, 1, 200)

    def leaveEvent(self, e):
        run_anim(self._ah, self._hov, 0, 260)

    def mousePressEvent(self, e):
        run_anim(self._ap, self._press, 1, 90)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        run_anim(self._ap, self._press, 0, 420, QEasingCurve.Type.OutBack)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        s = 1 - 0.04 * self._press
        p.translate(w / 2, h / 2)
        p.scale(s, s)
        p.translate(-w / 2, -h / 2)
        paint_glass(p, QRectF(1.5, 1.5, w - 3, h - 3), 22, THEME.accent if self._hov > 0.5 else None, self._hov)
        draw_icon(self.icon_name, p, QRectF(w / 2 - 15, 16, 30, 30), THEME.accent2 if THEME.dark else THEME.accent, 2.0)
        f = QFont(self.font())
        f.setPixelSize(15)
        f.setBold(True)
        draw_text(p, QRectF(10, 54, w - 20, 22), self.title, "center", THEME.text, f)
        f2 = QFont(self.font())
        f2.setPixelSize(11)
        opt = QTextOption(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        p.setFont(f2)
        p.setPen(THEME.sub)
        p.drawText(QRectF(14, 78, w - 28, h - 82), self.desc, opt)


# ------------------------------------------------------------------ small ui helpers
def icon_button(icon, size=38, kind="ghost", tip=""):
    b = GlassButton("", kind, icon, height=size)
    b.setFixedWidth(size)
    if tip:
        b.setToolTip(tip)
    return b


def wrap_scroll(widget):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sc.setWidget(widget)
    sc.viewport().setAutoFillBackground(False)
    widget.setAutoFillBackground(False)
    return sc


def setting_row(title, desc, widget):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 12, 0, 12)
    h.setSpacing(18)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(lbl(title, "h2"))
    if desc:
        col.addWidget(lbl(desc, "sub", True))
    h.addLayout(col, 1)
    h.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    return w


def page_title(title, sub=None):
    box = QVBoxLayout()
    box.setSpacing(2)
    box.addWidget(lbl(title, "h1"))
    if sub:
        box.addWidget(lbl(sub, "sub"))
    return box


def segmented(labels, on_change, checked=0):
    """Row of exclusive glass chips."""
    row = QHBoxLayout()
    row.setSpacing(8)
    grp = QButtonGroup()
    btns = []
    for i, t in enumerate(labels):
        b = GlassButton(t, "normal", height=36)
        b.setCheckable(True)
        grp.addButton(b, i)
        row.addWidget(b)
        btns.append(b)
    btns[checked].setChecked(True)
    grp.idClicked.connect(on_change)
    return row, grp, btns


class AccountForm(QWidget):
    """Manage multiple local/offline player names."""
    def __init__(self, main):
        super().__init__()
        self.m = main
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        self.avatar = QLabel()
        self.avatar.setFixedSize(76, 76)
        lay.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(lbl("Offline Accounts", "h2"))
        self.accounts = QComboBox()
        self.accounts.setMinimumWidth(220)
        self.accounts.currentTextChanged.connect(self.select_account)
        col.addWidget(self.accounts)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit(main.settings["username"])
        self.edit.setMaxLength(16)
        self.edit.setPlaceholderText("3-16 letters, numbers or _")
        row.addWidget(self.edit, 1)
        self.save = GlassButton("Save name", "accent", "check", height=40)
        self.save.setFixedWidth(120)
        self.save.clicked.connect(self.do_save)
        row.addWidget(self.save)
        col.addLayout(row)
        actions = QHBoxLayout()
        self.add_btn = GlassButton("Add account", "normal", "plus", height=38)
        self.add_btn.clicked.connect(self.add_account)
        self.remove_btn = GlassButton("Remove account", "ghost", "trash", height=38)
        self.remove_btn.clicked.connect(self.remove_account)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.remove_btn)
        actions.addStretch()
        col.addLayout(actions)
        self.hint = lbl("Each offline name can keep its own local skin and cape selection.", "sub", True)
        col.addWidget(self.hint)
        lay.addLayout(col, 1)
        self.edit.textChanged.connect(self.on_text)
        self.edit.returnPressed.connect(self.do_save)
        self.refresh()

    def _names(self):
        names = self.m.settings.get("offline_accounts", [])
        if not isinstance(names, list):
            names = []
        current = self.m.settings.get("username", "Player")
        cleaned = []
        for n in names + [current]:
            if isinstance(n, str) and NAME_RE.match(n) and n not in cleaned:
                cleaned.append(n)
        if not cleaned:
            cleaned = ["Player"]
        self.m.settings["offline_accounts"] = cleaned
        return cleaned

    def refresh(self):
        names = self._names()
        current = self.m.settings.get("username", "Player")
        self.accounts.blockSignals(True)
        self.accounts.clear()
        self.accounts.addItems(names)
        self.accounts.setCurrentText(current)
        self.accounts.blockSignals(False)
        self.edit.blockSignals(True)
        self.edit.setText(current)
        self.edit.blockSignals(False)
        self.avatar.setPixmap(letter_avatar(current, 76, 22))
        IMG.request(f"https://minotar.net/helm/{current}/76.png",
                    lambda pm, name=current: self.avatar.setPixmap(rounded_pix(pm, 76, 76, 22))
                    if self.m.settings.get("username") == name else None)
        self.remove_btn.setEnabled(len(names) > 1)

    def select_account(self, name):
        if not name or name == self.m.settings.get("username"):
            return
        self.m.save_username(name)

    def add_account(self):
        name = self.edit.text().strip()
        if not NAME_RE.match(name):
            self.m.toast("Enter a valid name (3-16 letters, numbers or _), then Add account", "err")
            return
        names = self._names()
        if name not in names:
            names.append(name)
        self.m.settings["offline_accounts"] = names
        self.m.save_username(name)
        self.refresh()
        self.m.toast(f"Offline account {name} added")

    def remove_account(self):
        name = self.accounts.currentText()
        names = self._names()
        if len(names) <= 1:
            self.m.toast("Keep at least one offline account", "err")
            return
        if name in names:
            names.remove(name)
        self.m.settings["offline_accounts"] = names
        if name == self.m.settings.get("username"):
            self.m.settings["username"] = names[0]
            self.m.save_username(names[0])
        else:
            save_json(SETTINGS_FILE, self.m.settings)
        self.refresh()
        self.m.toast(f"Removed offline account {name}")

    def on_text(self, _):
        same = self.edit.text().strip() == self.m.settings.get("username")
        self.hint.setObjectName("accent" if not same else "sub")
        self.hint.setText("Unsaved name — press Save name or Add account." if not same
                          else "Each offline name can keep its own local skin and cape selection.")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def do_save(self):
        name = self.edit.text().strip()
        if not NAME_RE.match(name):
            self.m.toast("Name must be 3-16 characters: letters, numbers or _", "err")
            return
        names = self._names()
        if name not in names:
            names.append(name)
        self.m.settings["offline_accounts"] = names
        self.m.save_username(name)
        self.refresh()
        self.save.setText("Saved")
        QTimer.singleShot(1600, lambda: call_safe(lambda: self.save.setText("Save name")))


# ================================================================== pages
class HomePage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(12)
        self.welcome = lbl("", "h1")
        left.addWidget(self.welcome)
        self.hero = Hero()
        hl = QVBoxLayout(self.hero)
        hl.addStretch()
        self.launch = GlassButton("LAUNCH GAME", "accent", height=78)
        self.launch.setSub("No profile")
        self.launch.setFixedWidth(380)
        self.launch.clicked.connect(lambda: m.start_launch(m.get_active()))
        hl.addWidget(self.launch, 0, Qt.AlignmentFlag.AlignHCenter)
        hl.addStretch()
        left.addWidget(self.hero, 1)
        left.addWidget(lbl("Latest News", "h2"))
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(NewsCard("Welcome to Zenith", "Fast, clean and fully yours.", "news-a"))
        row.addWidget(NewsCard("Any modpack, one click", "Import .mrpack or Prism .zip files.", "news-b"))
        row.addWidget(NewsCard("Make it yours", "Themes, glass level, own backgrounds.", "news-c"))
        left.addLayout(row)
        lay.addLayout(left, 1)

        right = Glass(26)
        right.setFixedWidth(330)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 18, 18, 18)
        rl.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(lbl("Profiles", "h1"))
        head.addStretch()
        add = icon_button("plus", 40, "normal", "New profile")
        add.clicked.connect(m.open_new_profile)
        head.addWidget(add)
        rl.addLayout(head)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(m.set_active)
        rl.addWidget(self.list, 1)
        self.empty = lbl("No profiles yet. Press + to create one.", "sub", True)
        rl.addWidget(self.empty)
        br = QHBoxLayout()
        br.setSpacing(8)
        for icon, tip, fn in (("settings", "Edit profile", m.open_edit_profile), ("folder", "Open folder", m.open_profile_folder),
                              ("trash", "Delete profile", m.open_delete_profile)):
            b = icon_button(icon, 42, "danger" if icon == "trash" else "normal", tip)
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        rl.addLayout(br)
        lay.addWidget(right)

    def refresh(self):
        m = self.m
        self.welcome.setText(f"Welcome back, {m.settings['username']}")
        self.list.blockSignals(True)
        self.list.clear()
        for p in m.profiles:
            self.list.addItem(QListWidgetItem(f"{p['name']}\n{p['loader']}  ·  Minecraft {p['mc']}"))
            self.list.item(self.list.count() - 1).setSizeHint(QSize(100, 62))
        if m.profiles:
            self.list.setCurrentRow(m.active)
        self.list.blockSignals(False)
        self.empty.setVisible(not m.profiles)
        p = m.get_active()
        self.launch.setSub(f"{p['name']}  ·  {p['loader']} {p['mc']}" if p else "No profile - create one first")


class VersionsPage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.sel = None
        self.cards = []
        self._cols = 0
        self.loader = "Vanilla"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = Glass(24)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(10)
        self.type_btns = []
        self.type_keys = ["release", "snapshot", "old_beta", "old_alpha"]
        self.type_names = ["Release", "Snapshot", "Old Beta", "Old Alpha"]
        self.typ = 0
        row, self.grp, self.type_btns = segmented(self.type_names, self.on_type)
        tl.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search versions...")
        self.search.textChanged.connect(self.render)
        tl.addWidget(self.search, 1)
        custom = GlassButton("Custom Import", "normal", "folder-open", height=40)
        custom.setToolTip("Import a .zip/.mrpack modpack or client instance")
        custom.clicked.connect(self.import_custom)
        tl.addWidget(custom)
        newp = GlassButton("New Profile", "accent", "plus", height=40)
        newp.clicked.connect(m.open_new_profile)
        tl.addWidget(newp)
        lay.addWidget(top)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cont = QWidget()
        cont.setAutoFillBackground(False)
        self.grid = QGridLayout(cont)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.grid.setSpacing(14)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(cont)
        self.scroll.viewport().setAutoFillBackground(False)
        row.addWidget(self.scroll, 1)

        det = Glass(26)
        det.setFixedWidth(310)
        dl = QVBoxLayout(det)
        dl.setContentsMargins(18, 18, 18, 18)
        dl.setSpacing(10)
        self.art = QLabel()
        self.art.setFixedSize(274, 150)
        dl.addWidget(self.art)
        self.title = lbl("Select a version", "h1")
        dl.addWidget(self.title)
        self.info = lbl("Pick a version card on the left.", "sub", True)
        dl.addWidget(self.info)
        dl.addStretch()
        dl.addWidget(lbl("Quick Version Selector", "h2"))
        self.version_selector = QComboBox()
        self.version_selector.setMinimumHeight(36)
        self.version_selector.setToolTip("Choose a version from the complete loaded list")
        self.version_selector.currentTextChanged.connect(self._quick_pick)
        dl.addWidget(self.version_selector)
        dl.addWidget(lbl("Loader", "h2"))
        lrow, self.lgrp, self.lbtns = segmented(LOADERS, self.on_loader)
        for b in self.lbtns:
            b.setFixedHeight(34)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, b in enumerate(self.lbtns):
            grid.addWidget(b, i // 2, i % 2)
        # segmented() already added buttons to a layout; re-parent them into the grid
        dl.addLayout(grid)
        self.iso = Switch(True)
        dl.addWidget(setting_row("Isolated profile", "Own worlds and mods", self.iso))
        cp = GlassButton("Create Profile", "normal", "plus", height=44)
        cp.clicked.connect(lambda: m.create_from_selection(self))
        dl.addWidget(cp)
        lb = GlassButton("Launch Game", "accent", "play", height=48)
        lb.clicked.connect(lambda: m.launch_selection(self))
        dl.addWidget(lb)
        row.addWidget(det)
        lay.addLayout(row, 1)

    def import_custom(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import custom client / modpack", "",
            "Minecraft packs (*.mrpack *.zip);;ZIP files (*.zip);;All files (*.*)")
        if path:
            self.m.start_import(Path(path))

    def _quick_pick(self, version_id):
        if not version_id:
            return
        v = next((x for x in self.m.all_versions if x["id"] == version_id), None)
        if v:
            self.pick(v)

    def on_type(self, i):
        self.typ = i
        self.render()

    def on_loader(self, i):
        self.loader = LOADERS[i]

    def render(self, *_):
        for c in self.cards:
            self.grid.removeWidget(c)
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        q = self.search.text().strip().lower()
        want = self.type_keys[self.typ]
        items = [v for v in self.m.all_versions if v["type"] == want and q in v["id"].lower()]
        current_selector = self.version_selector.currentText()
        self.version_selector.blockSignals(True)
        self.version_selector.clear()
        self.version_selector.addItems([v["id"] for v in self.m.all_versions])
        if self.sel:
            idx = self.version_selector.findText(self.sel)
            if idx >= 0:
                self.version_selector.setCurrentIndex(idx)
        elif current_selector:
            idx = self.version_selector.findText(current_selector)
            if idx >= 0:
                self.version_selector.setCurrentIndex(idx)
        self.version_selector.blockSignals(False)
        grp = QButtonGroup(self)
        self._cgrp = grp
        for v in items:
            c = VersionCard(v["id"], v["type"])
            c.clicked.connect(lambda _, vv=v: self.pick(vv))
            if v["id"] == self.sel:
                c.setChecked(True)
            grp.addButton(c)
            self.cards.append(c)
        self._cols = 0
        self.relayout()

    def relayout(self):
        cols = max(1, (self.scroll.viewport().width() - 8) // (CARD_W + 14))
        if cols == self._cols:
            return
        self._cols = cols
        for c in self.cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.relayout)

    def pick(self, v):
        self.sel = v["id"]
        self.title.setText(f"Minecraft {v['id']}")
        self.info.setText(f"Type: {v['type'].replace('_', ' ')}\nReleased: {v.get('releaseTime', '')[:10] or 'n/a'}")
        self.art.setPixmap(rounded_pix(get_cover(v["id"], 274, 150), 274, 150, 20))

    def select_default(self):
        rel = [v for v in self.m.all_versions if v["type"] == "release"]
        if rel and not self.sel:
            self.pick(rel[0])


class ModRow(Glass):
    def __init__(self, title, desc, meta, icon_url=None):
        super().__init__(22)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 12)
        self.lay.setSpacing(14)
        self.icon = QLabel()
        self.icon.setFixedSize(58, 58)
        self.icon.setPixmap(letter_avatar(title, 58, 16))
        self.lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        if icon_url:
            IMG.request(icon_url, lambda pm: self.icon.setPixmap(rounded_pix(pm, 58, 58, 16)))
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(lbl(title, "h2"))
        if desc:
            col.addWidget(lbl(desc, "sub", True))
        if meta:
            col.addWidget(lbl(meta, "sub"))
        self.lay.addLayout(col, 1)


class ModsPage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.mode = 0  # 0 installed, 1 explore, 2 modpacks
        self.token = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = Glass(24)
        tl = QVBoxLayout(top)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(10)
        r1 = QHBoxLayout()
        row, self.grp, self.tabs = segmented(["Installed", "Explore Mods", "Modpacks"], self.on_tab)
        r1.addLayout(row)
        r1.addStretch()
        r1.addWidget(lbl("Profile", "sub"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        self.combo.currentIndexChanged.connect(self.on_profile)
        r1.addWidget(self.combo)
        tl.addLayout(r1)
        self.r2 = QWidget()
        r2 = QHBoxLayout(self.r2)
        r2.setContentsMargins(0, 0, 0, 0)
        r2.setSpacing(10)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search Modrinth...")
        self.query.returnPressed.connect(self.search)
        self.sort = QComboBox()
        for t, k in (("Relevance", "relevance"), ("Downloads", "downloads"), ("Newest", "newest"), ("Updated", "updated")):
            self.sort.addItem(t, k)
        self.sort.setCurrentIndex(1)
        self.sort.currentIndexChanged.connect(self.search)
        sb = GlassButton("Search", "accent", "search", height=40)
        sb.clicked.connect(self.search)
        r2.addWidget(self.query, 1)
        r2.addWidget(self.sort)
        r2.addWidget(sb)
        tl.addWidget(self.r2)
        lay.addWidget(top)
        self.body = QWidget()
        self.body.setAutoFillBackground(False)
        self.blay = QVBoxLayout(self.body)
        self.blay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.blay.setSpacing(10)
        self.blay.setContentsMargins(2, 2, 6, 2)
        sc = wrap_scroll(self.body)
        lay.addWidget(sc, 1)
        self.set_mode(0)

    def on_tab(self, i):
        self.set_mode(i)

    def set_mode(self, i):
        self.mode = i
        self.tabs[i].setChecked(True)
        self.r2.setVisible(i > 0)
        self.query.setPlaceholderText("Search mods on Modrinth..." if i == 1 else "Search modpacks on Modrinth...")
        self.combo.setVisible(i != 2)
        self.refresh()

    def refresh_profiles(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        for p in self.m.profiles:
            self.combo.addItem(f"{p['name']}  ({p['loader']} {p['mc']})")
        if self.m.profiles:
            self.combo.setCurrentIndex(self.m.active)
        self.combo.blockSignals(False)

    def on_profile(self, i):
        if i >= 0 and i != self.m.active:
            self.m.set_active(i)
        if self.mode == 0:
            self.refresh()
        elif self.mode == 1:
            self.search()

    def clear(self):
        clear_layout(self.blay)

    def empty_state(self, text, button=None, fn=None):
        box = Glass(24)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(30, 36, 30, 36)
        bl.setSpacing(12)
        bl.addWidget(lbl(text, "h2"), 0, Qt.AlignmentFlag.AlignHCenter)
        if button:
            b = GlassButton(button, "accent", "search", height=42)
            b.clicked.connect(fn)
            bl.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        self.blay.addWidget(box)

    def refresh(self):
        self.clear()
        if self.mode == 0:
            self.render_installed()
        else:
            if not self.query.text().strip() and self.blay.count() == 0:
                pass
            self.search()

    def render_installed(self):
        p = self.m.get_active()
        if not p:
            self.empty_state("No profile selected")
            return
        mods_dir = Path(game_dir(p)) / "mods"
        files = sorted([f for f in mods_dir.glob("*") if f.name.endswith((".jar", ".jar.disabled"))],
                       key=lambda f: f.name.lower()) if mods_dir.exists() else []
        top = QHBoxLayout()
        top.addWidget(lbl(f"{len(files)} mod(s) in {p['name']}", "sub"))
        top.addStretch()
        ob = GlassButton("Open mods folder", "normal", "folder", height=36)
        ob.clicked.connect(lambda: open_path(mods_dir))
        top.addWidget(ob)
        w = QWidget()
        w.setLayout(top)
        self.blay.addWidget(w)
        if not files:
            self.empty_state("No mods found. Minecraft is better with mods!", "Explore Mods", lambda: self.set_mode(1))
            return
        for f in files:
            enabled = f.name.endswith(".jar")
            nm = f.name.replace(".jar.disabled", "").replace(".jar", "")
            row = ModRow(nm, "", f"{f.stat().st_size / 1048576:.2f} MB")
            sw = Switch(enabled)
            sw.toggled.connect(lambda on, ff=f: self.toggle_mod(ff, on))
            row.lay.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
            tb = icon_button("trash", 40, "danger", "Delete mod")
            tb.clicked.connect(lambda _, ff=f: self.delete_mod(ff))
            row.lay.addWidget(tb, 0, Qt.AlignmentFlag.AlignVCenter)
            self.blay.addWidget(row)

    def toggle_mod(self, f, on):
        try:
            new = f.with_name(f.name[:-9] if on and f.name.endswith(".disabled") else (f.name + ".disabled" if not on and f.name.endswith(".jar") else f.name))
            if new != f:
                f.rename(new)
            QTimer.singleShot(400, self.refresh)
        except Exception as ex:
            self.m.toast(f"Could not change mod: {ex}", "err")

    def delete_mod(self, f):
        try:
            f.unlink()
            self.m.toast("Mod removed")
            self.refresh()
        except Exception as ex:
            self.m.toast(f"Could not delete: {ex}", "err")

    def search(self, *_):
        if self.mode == 0:
            return
        self.token += 1
        tok = self.token
        q = self.query.text().strip()
        p = self.m.get_active()
        kind = "mod" if self.mode == 1 else "modpack"
        sort = self.sort.currentData()
        self.clear()
        self.blay.addWidget(lbl("Searching...", "sub"))
        threading.Thread(target=self.search_worker, args=(tok, kind, q, sort, dict(p) if p else None), daemon=True).start()

    def search_worker(self, tok, kind, q, sort, p):
        try:
            facets = [[f"project_type:{kind}"]]
            if kind == "mod" and p:
                facets.append([f"versions:{p['mc']}"])
                if p["loader"] != "Vanilla":
                    facets.append([f"categories:{p['loader'].lower()}"])
            r = requests.get(f"{MODRINTH}/search", headers=UA, timeout=20,
                             params={"query": q, "limit": 30, "index": sort, "facets": json.dumps(facets)})
            r.raise_for_status()
            hits = r.json().get("hits", [])
            self.m.ui(lambda: self.render_hits(tok, kind, hits))
        except Exception as ex:
            self.m.ui(lambda: self.render_error(tok, str(ex)))

    def render_error(self, tok, msg):
        if tok != self.token:
            return
        self.clear()
        self.empty_state(f"Search failed: {msg}")

    def render_hits(self, tok, kind, hits):
        if tok != self.token or self.mode == 0:
            return
        self.clear()
        if not hits:
            self.empty_state("Nothing found for this profile / search.")
            return
        for h in hits:
            cats = ", ".join(c.title() for c in h.get("display_categories", [])[:3])
            meta = f"by {h.get('author', '?')}   ·   {h.get('downloads', 0):,} downloads" + (f"   ·   {cats}" if cats else "")
            row = ModRow(h["title"], h.get("description", ""), meta, h.get("icon_url"))
            vb = GlassButton("View", "normal", height=38)
            slug = h.get("slug", h["project_id"])
            vb.clicked.connect(lambda _, s=slug, k=kind: QDesktopServices.openUrl(QUrl(f"https://modrinth.com/{k}/{s}")))
            ib = GlassButton("Install", "accent", "download", height=38)
            ib.clicked.connect(lambda _, pid=h["project_id"], t=h["title"], k=kind: self.m.install_project(pid, t, k))
            row.lay.addWidget(vb, 0, Qt.AlignmentFlag.AlignVCenter)
            row.lay.addWidget(ib, 0, Qt.AlignmentFlag.AlignVCenter)
            self.blay.addWidget(row)


class ServersPage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.rows = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = Glass(24)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 12, 14, 12)
        tl.addLayout(page_title("Servers", "Add your favourite servers and join with one click."))
        tl.addStretch()
        rf = GlassButton("Refresh", "normal", "update", height=40)
        rf.clicked.connect(self.refresh)
        tl.addWidget(rf)
        add = GlassButton("Add Server", "accent", "plus", height=40)
        add.clicked.connect(m.open_add_server)
        tl.addWidget(add)
        lay.addWidget(top)
        self.body = QWidget()
        self.body.setAutoFillBackground(False)
        self.blay = QVBoxLayout(self.body)
        self.blay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.blay.setSpacing(10)
        self.blay.setContentsMargins(2, 2, 6, 2)
        lay.addWidget(wrap_scroll(self.body), 1)

    def refresh(self):
        clear_layout(self.blay)
        self.rows = {}
        if not self.m.servers:
            box = Glass(24)
            bl = QVBoxLayout(box)
            bl.setContentsMargins(30, 40, 30, 40)
            bl.setSpacing(12)
            bl.addWidget(lbl("No servers yet", "h1"), 0, Qt.AlignmentFlag.AlignHCenter)
            bl.addWidget(lbl("Press Add Server and type a name and an address.", "sub"), 0, Qt.AlignmentFlag.AlignHCenter)
            self.blay.addWidget(box)
            return
        for i, s in enumerate(self.m.servers):
            row = ModRow(s["name"], s["address"], "Checking status...")
            texts = row.findChildren(QLabel)
            status = texts[-1]
            play = GlassButton("Play", "accent", "play", height=40)
            play.clicked.connect(lambda _, a=s["address"]: self.m.start_launch(self.m.get_active(), a))
            rm = icon_button("trash", 40, "danger", "Remove")
            rm.clicked.connect(lambda _, idx=i: self.m.remove_server(idx))
            row.lay.addWidget(play, 0, Qt.AlignmentFlag.AlignVCenter)
            row.lay.addWidget(rm, 0, Qt.AlignmentFlag.AlignVCenter)
            self.blay.addWidget(row)
            self.rows[s["address"]] = (row, status)
            threading.Thread(target=self.m.fetch_server_status, args=(s["address"],), daemon=True).start()

    def apply_status(self, addr, res):
        if addr not in self.rows:
            return
        row, status = self.rows[addr]
        def go():
            if res.get("online") is None:
                status.setText("Status unavailable")
            elif res["online"]:
                pl = res.get("players", {})
                status.setText(f"● Online   {pl.get('online', 0)}/{pl.get('max', 0)} players   {res.get('motd', '')[:60]}")
            else:
                status.setText("● Offline")
            if res.get("icon"):
                import base64
                try:
                    data = base64.b64decode(res["icon"].split(",", 1)[1])
                    pm = QPixmap()
                    if pm.loadFromData(data):
                        row.icon.setPixmap(rounded_pix(pm, 58, 58, 16))
                except Exception:
                    pass
        call_safe(go)


class ThemesPage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        top = Glass(24)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 12, 14, 12)
        tl.addLayout(page_title("Themes", "Pick a look. It applies instantly and is saved automatically."))
        lay.addWidget(top)
        inner = QWidget()
        inner.setAutoFillBackground(False)
        il = QVBoxLayout(inner)
        il.setContentsMargins(2, 2, 6, 2)
        il.setSpacing(14)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {}
        self.grp = QButtonGroup(self)
        for i, name in enumerate(THEMES):
            c = ThemeCard(name)
            c.clicked.connect(lambda _, n=name: m.apply_theme(name=n))
            self.grp.addButton(c)
            self.cards[name] = c
            grid.addWidget(c, i // 4, i % 4)
        grid.setColumnStretch(4, 1)
        il.addLayout(grid)
        panel = Glass(26)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(22, 14, 22, 14)
        pl.addWidget(lbl("Appearance", "h1"))
        self.glass = QSlider(Qt.Orientation.Horizontal)
        self.glass.setRange(0, 100)
        self.glass.setValue(m.settings["glass"])
        self.glass.setFixedWidth(260)
        self.glass.valueChanged.connect(lambda v: m.apply_theme(glass=v, save=False))
        self.glass.sliderReleased.connect(lambda: m.apply_theme(glass=self.glass.value(), toast=True))
        pl.addWidget(setting_row("Glass intensity", "How frosted the panels look", self.glass))
        pl.addWidget(Divider())
        self.anim_bg = Switch(m.settings["anim_bg"])
        self.anim_bg.toggled.connect(lambda v: m.apply_theme(anim=v, toast=True))
        pl.addWidget(setting_row("Animated background", "Slowly moving colour glow behind the glass", self.anim_bg))
        pl.addWidget(Divider())
        self.smooth = Switch(m.settings["smooth"])
        self.smooth.toggled.connect(lambda v: m.apply_theme(smooth=v, toast=True))
        pl.addWidget(setting_row("Smooth animations", "Button ripples, page fades and bounce effects", self.smooth))
        pl.addWidget(Divider())
        bgrow = QHBoxLayout()
        bgrow.setSpacing(8)
        pick = GlassButton("Choose image", "normal", "image", height=40)
        pick.clicked.connect(m.choose_background)
        rem = GlassButton("Remove", "danger", "trash", height=40)
        rem.clicked.connect(m.remove_background)
        bgrow.addWidget(pick)
        bgrow.addWidget(rem)
        bw = QWidget()
        bw.setLayout(bgrow)
        pl.addWidget(setting_row("Custom background", "Use your own picture behind the launcher", bw))
        pl.addWidget(Divider())
        cov = GlassButton("Open covers folder", "normal", "folder", height=40)
        cov.clicked.connect(lambda: open_path(COVERS_DIR))
        pl.addWidget(setting_row("Version card pictures",
                                 "Put images named like 1.21.1.png in this folder to replace a version's art", cov))
        il.addWidget(panel)
        il.addStretch()
        lay.addWidget(wrap_scroll(inner), 1)
        self.sync()

    def sync(self):
        for n, c in self.cards.items():
            c.setChecked(n == self.m.settings["theme"])


class ProfilePage(QWidget):
    """Local player cosmetics manager: one skin and three cape image slots."""
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.cosmetics_dir = HOME / "cosmetics"
        self.cosmetics_dir.mkdir(parents=True, exist_ok=True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 8)
        lay.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        head = Glass(24)
        hl = QVBoxLayout(head)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.addWidget(lbl("Player Profile", "h1"))
        hl.addWidget(lbl("Choose one skin and up to three cape designs.", "sub", True))
        lay.addWidget(head)

        note = Glass(18)
        nl = QVBoxLayout(note)
        nl.setContentsMargins(16, 12, 16, 12)
        nl.addWidget(lbl("Important: local setup only", "h2"))
        nl.addWidget(lbl("These images are saved in Zenith on this PC. This offline launcher cannot upload them to your official Minecraft account or make them appear on multiplayer servers by itself. That requires Microsoft/Minecraft account authentication or a compatible cosmetics mod.", "sub", True))
        lay.addWidget(note)

        skin_card = Glass(24)
        sl = QHBoxLayout(skin_card)
        sl.setContentsMargins(18, 16, 18, 16)
        sl.setSpacing(16)
        self.skin_preview = QLabel()
        self.skin_preview.setFixedSize(110, 150)
        self.skin_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skin_preview.setPixmap(letter_avatar("SKIN", 88, 20))
        sl.addWidget(self.skin_preview)
        sc = QVBoxLayout()
        sc.addWidget(lbl("Minecraft Skin", "h2"))
        sc.addWidget(lbl("Select a PNG skin file (classic or slim model).", "sub", True))
        self.skin_path = lbl("No skin selected", "sub", True)
        sc.addWidget(self.skin_path)
        sb = GlassButton("Choose Skin", "accent", "image", height=42)
        sb.clicked.connect(self.choose_skin)
        sc.addWidget(sb)
        sr = GlassButton("Remove Skin", "ghost", "trash", height=38)
        sr.clicked.connect(self.remove_skin)
        sc.addWidget(sr)
        sc.addStretch()
        sl.addLayout(sc, 1)
        lay.addWidget(skin_card)

        cape_head = Glass(20)
        ch = QVBoxLayout(cape_head)
        ch.setContentsMargins(18, 14, 18, 14)
        ch.addWidget(lbl("Cape Collection · 3 Slots", "h2"))
        ch.addWidget(lbl("Add up to three cape PNGs and keep them saved here.", "sub", True))
        lay.addWidget(cape_head)

        self.cape_previews = []
        self.cape_paths = []
        row = QHBoxLayout()
        row.setSpacing(12)
        for i in range(3):
            card = Glass(22)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 14, 12, 14)
            cl.setSpacing(8)
            cl.addWidget(lbl(f"Cape {i + 1}", "h2"))
            preview = QLabel()
            preview.setFixedSize(140, 92)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setPixmap(letter_avatar("CAPE", 80, 18))
            cl.addWidget(preview, 0, Qt.AlignmentFlag.AlignHCenter)
            path_lbl = lbl("Empty slot", "sub", True)
            path_lbl.setWordWrap(True)
            cl.addWidget(path_lbl)
            choose = GlassButton("Choose PNG", "normal", "image", height=38)
            choose.clicked.connect(lambda _, slot=i: self.choose_cape(slot))
            cl.addWidget(choose)
            remove = GlassButton("Clear", "ghost", "trash", height=34)
            remove.clicked.connect(lambda _, slot=i: self.remove_cape(slot))
            cl.addWidget(remove)
            row.addWidget(card, 1)
            self.cape_previews.append((preview, path_lbl))
            self.cape_paths.append("")
        lay.addLayout(row)
        lay.addStretch()
        self.load_saved()

    def _copy_image(self, source, name):
        ext = Path(source).suffix.lower() or ".png"
        dest = self.cosmetics_dir / f"{name}{ext}"
        try:
            shutil.copy2(source, dest)
        except Exception as ex:
            self.m.toast(f"Could not save image: {ex}", "err")
            return ""
        return str(dest)

    def _preview(self, path, target, size):
        if path and Path(path).is_file():
            pm = QPixmap(path)
            if not pm.isNull():
                target.setPixmap(pm.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))
                return
        target.setPixmap(letter_avatar("SKIN" if target is self.skin_preview else "CAPE", 80, 18))

    def load_saved(self):
        # Cosmetics are stored separately for each offline player name.
        all_cosmetics = self.m.settings.get("cosmetics_by_account", {})
        if not isinstance(all_cosmetics, dict):
            all_cosmetics = {}
        account = self.m.settings.get("username", "Player")
        saved_account = all_cosmetics.get(account, {})
        if isinstance(saved_account, dict):
            self.m.settings["cosmetic_skin"] = saved_account.get("skin", self.m.settings.get("cosmetic_skin", ""))
            self.m.settings["cosmetic_capes"] = saved_account.get("capes", self.m.settings.get("cosmetic_capes", ["", "", ""]))
        self.skin_file = self.m.settings.get("cosmetic_skin", "")
        self.skin_path.setText(Path(self.skin_file).name if self.skin_file and Path(self.skin_file).is_file() else "No skin selected")
        self._preview(self.skin_file, self.skin_preview, QSize(110, 150))
        saved = self.m.settings.get("cosmetic_capes", ["", "", ""])
        if not isinstance(saved, list):
            saved = ["", "", ""]
        for i in range(3):
            path = saved[i] if i < len(saved) else ""
            self.cape_paths[i] = path if path and Path(path).is_file() else ""
            preview, label = self.cape_previews[i]
            label.setText(Path(self.cape_paths[i]).name if self.cape_paths[i] else "Empty slot")
            self._preview(self.cape_paths[i], preview, QSize(140, 92))

    def _save(self):
        self.m.settings["cosmetic_skin"] = getattr(self, "skin_file", "")
        self.m.settings["cosmetic_capes"] = self.cape_paths[:3]
        all_cosmetics = self.m.settings.get("cosmetics_by_account", {})
        if not isinstance(all_cosmetics, dict):
            all_cosmetics = {}
        all_cosmetics[self.m.settings.get("username", "Player")] = {
            "skin": self.m.settings["cosmetic_skin"],
            "capes": self.cape_paths[:3],
        }
        self.m.settings["cosmetics_by_account"] = all_cosmetics
        save_json(SETTINGS_FILE, self.m.settings)

    def choose_skin(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose Minecraft skin", "", "PNG images (*.png)")
        if not f:
            return
        path = self._copy_image(f, "skin")
        if not path:
            return
        self.skin_file = path
        self.skin_path.setText(Path(path).name)
        self._preview(path, self.skin_preview, QSize(110, 150))
        self._save()
        self.m.toast("Skin saved locally")

    def remove_skin(self):
        self.skin_file = ""
        self.skin_path.setText("No skin selected")
        self._preview("", self.skin_preview, QSize(110, 150))
        self._save()
        self.m.toast("Skin selection cleared")

    def choose_cape(self, slot):
        f, _ = QFileDialog.getOpenFileName(self, f"Choose Cape {slot + 1}", "", "PNG images (*.png)")
        if not f:
            return
        path = self._copy_image(f, f"cape_{slot + 1}")
        if not path:
            return
        self.cape_paths[slot] = path
        preview, label = self.cape_previews[slot]
        label.setText(Path(path).name)
        self._preview(path, preview, QSize(140, 92))
        self._save()
        self.m.toast(f"Cape {slot + 1} saved locally")

    def remove_cape(self, slot):
        self.cape_paths[slot] = ""
        preview, label = self.cape_previews[slot]
        label.setText("Empty slot")
        self._preview("", preview, QSize(140, 92))
        self._save()
        self.m.toast(f"Cape {slot + 1} cleared")


class SettingsPage(QWidget):
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.loading = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = Glass(26)
        left.setFixedWidth(220)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 18, 14, 18)
        ll.setSpacing(6)
        ll.addWidget(lbl("Settings", "h1"))
        self.stack = QStackedWidget()
        self.grp = QButtonGroup(self)
        self.cats = []
        for i, (n, ic) in enumerate([("Game", "versions"), ("Account", "user"), ("General", "settings"),
                                     ("Storage", "folder"), ("Updates", "update")]):
            b = GlassButton(n, "ghost", ic, height=44, align="left")
            b.setCheckable(True)
            self.grp.addButton(b, i)
            ll.addWidget(b)
            self.cats.append(b)
        ll.addStretch()
        ll.addWidget(lbl(f"{APP_NAME} v{APP_VERSION}", "sub"))
        self.cats[0].setChecked(True)
        self.grp.idClicked.connect(lambda i: self.stack.setCurrentIndex(i))
        lay.addWidget(left)

        right = Glass(26)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.addWidget(self.stack)
        lay.addWidget(right, 1)

        ram = total_ram_mb()
        # ---- game
        g = QWidget()
        gl = QVBoxLayout(g)
        gl.setContentsMargins(22, 14, 22, 100)
        gl.addWidget(lbl("Game Settings", "h1"))
        mb = QWidget()
        mbl = QVBoxLayout(mb)
        mbl.setContentsMargins(0, 12, 0, 12)
        hr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(lbl("Allocated Memory", "h2"))
        col.addWidget(lbl("How much RAM the game may use", "sub"))
        hr.addLayout(col, 1)
        self.mem_lbl = lbl("", "accent")
        hr.addWidget(self.mem_lbl)
        mbl.addLayout(hr)
        self.mem = QSlider(Qt.Orientation.Horizontal)
        self.mem.setRange(2, max(4, ram // 256))
        self.mem.valueChanged.connect(self.on_mem)
        mbl.addWidget(self.mem)
        mbl.addWidget(lbl(f"512 MB  ...  {ram / 1024:.0f} GB (your total RAM)", "sub"))
        gl.addWidget(mb)
        gl.addWidget(Divider())
        rr = QHBoxLayout()
        rr.setSpacing(8)
        self.w = QSpinBox()
        self.w.setRange(320, 7680)
        self.h = QSpinBox()
        self.h.setRange(240, 4320)
        for sp in (self.w, self.h):
            sp.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            sp.setFixedWidth(90)
            sp.valueChanged.connect(self.check_dirty)
        rr.addWidget(self.w)
        rr.addWidget(lbl("×"))
        rr.addWidget(self.h)
        rw = QWidget()
        rw.setLayout(rr)
        gl.addWidget(setting_row("Game Resolution", "Window size of the game", rw))
        gl.addWidget(Divider())
        self.full = Switch()
        self.full.toggled.connect(self.check_dirty)
        gl.addWidget(setting_row("Launch in fullscreen", None, self.full))
        gl.addWidget(Divider())
        self.jvm = QLineEdit()
        self.jvm.setFixedWidth(280)
        self.jvm.setPlaceholderText("-XX:+UseG1GC ...")
        self.jvm.textChanged.connect(self.check_dirty)
        gl.addWidget(setting_row("Extra JVM arguments", "Advanced - leave empty if unsure", self.jvm))
        gl.addStretch()
        self.stack.addWidget(wrap_scroll(g))

        # ---- account
        a = QWidget()
        al = QVBoxLayout(a)
        al.setContentsMargins(22, 14, 22, 100)
        al.addWidget(lbl("Account", "h1"))
        al.addSpacing(8)
        self.account = AccountForm(m)
        al.addWidget(self.account)
        al.addSpacing(10)
        al.addWidget(lbl("Offline mode does not need a Microsoft login. Servers that require a real "
                         "(online-mode) account will not accept this name.", "sub", True))
        al.addStretch()
        self.stack.addWidget(wrap_scroll(a))

        # ---- general
        ge = QWidget()
        gel = QVBoxLayout(ge)
        gel.setContentsMargins(22, 14, 22, 100)
        gel.addWidget(lbl("General Settings", "h1"))
        jr = QHBoxLayout()
        jr.setSpacing(8)
        self.java = QLineEdit()
        self.java.setFixedWidth(240)
        self.java.setPlaceholderText("Automatic")
        self.java.textChanged.connect(self.check_dirty)
        bj = GlassButton("Browse", "normal", "folder", height=40)
        bj.clicked.connect(self.browse_java)
        jr.addWidget(self.java)
        jr.addWidget(bj)
        jw = QWidget()
        jw.setLayout(jr)
        gel.addWidget(setting_row("Java path", "Leave empty and the launcher downloads the right Java for you", jw))
        gel.addStretch()
        self.stack.addWidget(wrap_scroll(ge))

        # ---- storage
        st = QWidget()
        stl = QVBoxLayout(st)
        stl.setContentsMargins(22, 14, 22, 100)
        stl.addWidget(lbl("Storage Settings", "h1"))
        stl.addWidget(lbl(f"Data folder: {HOME}", "sub", True))
        self.size_lbl = lbl("Size: not calculated yet", "accent")
        stl.addWidget(self.size_lbl)
        stl.addSpacing(8)
        for text, ic, fn in (("Calculate size", "update", self.calc_size), ("Open data folder", "folder", lambda: open_path(HOME)),
                             ("Open last launch log", "folder", self.open_log), ("Clear cache", "trash", self.clear_cache)):
            b = GlassButton(text, "danger" if ic == "trash" else "normal", ic, height=42, align="left")
            b.setFixedWidth(240)
            b.clicked.connect(fn)
            stl.addWidget(b)
        stl.addStretch()
        self.stack.addWidget(wrap_scroll(st))

        # ---- updates
        up = QWidget()
        ul = QVBoxLayout(up)
        ul.setContentsMargins(22, 14, 22, 100)
        ul.addWidget(lbl("Updates", "h1"))
        ul.addWidget(lbl(f"Installed version: v{APP_VERSION}", "accent"))
        self.repo = QLineEdit()
        self.repo.setFixedWidth(280)
        self.repo.setPlaceholderText("yourname/zenith-launcher")
        self.repo.textChanged.connect(self.check_dirty)
        ul.addWidget(setting_row("GitHub repository", "The public repo where you publish new releases", self.repo))
        ul.addWidget(Divider())
        self.auto_up = Switch()
        self.auto_up.toggled.connect(self.check_dirty)
        ul.addWidget(setting_row("Check on startup", "Shows an Update button when a new version exists", self.auto_up))
        ul.addWidget(Divider())
        cb = GlassButton("Check for updates", "accent", "update", height=44)
        cb.setFixedWidth(240)
        cb.clicked.connect(lambda: m.check_update(manual=True))
        ul.addSpacing(6)
        ul.addWidget(cb)
        ul.addSpacing(10)
        ul.addWidget(lbl("How to publish an update: build the exe, open your repo on GitHub, go to Releases, "
                         "create a release with a higher tag (example v1.1.1) and upload ZenithLauncher.exe. "
                         "Every launcher then shows an Update button.", "sub", True))
        ul.addStretch()
        self.stack.addWidget(wrap_scroll(up))

        # ---- save bar
        self.bar = Glass(26, QColor("#f59e0b"), self)
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(22, 10, 12, 10)
        bl.setSpacing(10)
        bl.addWidget(lbl("You have unsaved changes", "h2"))
        self.discard = GlassButton("Discard", "ghost", height=40)
        self.discard.clicked.connect(self.load)
        self.savebtn = GlassButton("Save changes", "accent", "save", height=40)
        self.savebtn.clicked.connect(self.do_save)
        bl.addWidget(self.discard)
        bl.addWidget(self.savebtn)
        self.bar.adjustSize()
        self._bt = 0.0
        self._ba = make_anim(self, self._set_bt)
        self.bar_on = False
        self.load()
        self.place_bar()

    def select(self, i):
        self.cats[i].click()

    def on_mem(self, v):
        self.mem_lbl.setText(f"{v * 256 / 1024:.2f} GB")
        self.check_dirty()

    def browse_java(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select java executable")
        if f:
            self.java.setText(f)

    def calc_size(self):
        total = 0
        for root, _, files in os.walk(HOME):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        self.size_lbl.setText(f"Size: {total / 1048576:.1f} MB")

    def open_log(self):
        if LOG_FILE.exists():
            if os.name == "nt":
                os.startfile(str(LOG_FILE))
            else:
                open_path(HOME)
        else:
            self.m.toast("No launch log yet", "err")

    def clear_cache(self):
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.m.toast("Cache cleared")

    def collect(self):
        return {"memory": self.mem.value() * 256, "width": self.w.value(), "height": self.h.value(),
                "fullscreen": self.full.isChecked(), "jvm_args": self.jvm.text().strip(),
                "java_path": self.java.text().strip(), "update_repo": self.repo.text().strip(),
                "auto_update": self.auto_up.isChecked()}

    def load(self):
        s = self.m.settings
        self.loading = True
        self.mem.setValue(max(2, s["memory"] // 256))
        self.mem_lbl.setText(f"{self.mem.value() * 256 / 1024:.2f} GB")
        self.w.setValue(s["width"])
        self.h.setValue(s["height"])
        self.full.setChecked(s["fullscreen"])
        self.jvm.setText(s["jvm_args"])
        self.java.setText(s["java_path"])
        self.repo.setText(s["update_repo"])
        self.auto_up.setChecked(s["auto_update"])
        self.loading = False
        self.account.refresh()
        self.check_dirty()

    def check_dirty(self, *_):
        if self.loading:
            return
        s = self.m.settings
        dirty = any(s[k] != v for k, v in self.collect().items())
        self.set_bar(dirty)

    def do_save(self):
        self.m.apply_settings(self.collect())
        self.savebtn.setText("Saved")
        QTimer.singleShot(900, lambda: call_safe(lambda: (self.savebtn.setText("Save changes"), self.set_bar(False))))

    def set_bar(self, on):
        if on == self.bar_on:
            return
        self.bar_on = on
        run_anim(self._ba, self._bt, 1 if on else 0, 420 if on else 260,
                 QEasingCurve.Type.OutBack if on else QEasingCurve.Type.InCubic)

    def _set_bt(self, v):
        self._bt = v
        self.place_bar()

    def place_bar(self):
        self.bar.adjustSize()
        bw, bh = self.bar.width(), self.bar.height()
        x = (self.width() - bw) // 2
        y = self.height() - int((bh + 22) * self._bt) + (0 if self._bt > 0 else 40)
        self.bar.move(x, y)
        self.bar.setVisible(self._bt > 0.01)
        self.bar.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.place_bar()


# ================================================================== main window
class Main(QMainWindow):
    ui_call = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        for d in (HOME, MC_DIR, PROFILES_DIR, COVERS_DIR, CACHE_DIR):
            d.mkdir(parents=True, exist_ok=True)
        self.settings = {**DEFAULT_SETTINGS, **load_json(SETTINGS_FILE, {})}
        if not self.settings.get("update_repo") and DEFAULT_UPDATE_REPO:
            self.settings["update_repo"] = DEFAULT_UPDATE_REPO
        THEME.set(self.settings["theme"], self.settings["glass"])
        THEME.smooth = bool(self.settings["smooth"])
        QApplication.instance().setStyleSheet(build_qss())
        self.profiles = load_json(PROFILES_FILE, [])
        self.servers = load_json(SERVERS_FILE, [])
        self.active = 0 if self.profiles else -1
        self.all_versions = []
        self.busy = False
        self.overlay = None
        self.update_info = None
        self.ui_call.connect(lambda f: f())

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(make_logo(128)))
        self.resize(1260, 800)
        self.setMinimumSize(1020, 660)

        self.bg = Background()
        self.bg.animate = bool(self.settings["anim_bg"])
        self.bg.set_image(self.settings["bg_image"])
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        root.addWidget(self.build_topbar())
        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)
        body.addWidget(self.build_sidebar())
        self.stack = FadeStack()
        body.addWidget(self.stack, 1)
        self.home = HomePage(self)
        self.versions = VersionsPage(self)
        self.mods = ModsPage(self)
        self.servers_page = ServersPage(self)
        self.profile_page = ProfilePage(self)
        self.themes = ThemesPage(self)
        self.settings_page = SettingsPage(self)
        for pg in (self.home, self.versions, self.mods, self.servers_page, self.profile_page, self.themes, self.settings_page):
            self.stack.addWidget(pg)
        root.addWidget(self.build_footer())

        self.toaster = Toast(self.bg)
        self.refresh_account()
        self.refresh_profiles()
        self.servers_page.refresh()
        threading.Thread(target=self.fetch_versions, daemon=True).start()
        if self.settings["auto_update"] and self.settings["update_repo"]:
            QTimer.singleShot(3500, lambda: self.check_update(manual=False))

    # ---------------- build chrome
    def build_topbar(self):
        bar = Glass(26)
        bar.setFixedHeight(64)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(18, 8, 14, 8)
        bl.setSpacing(12)
        self.logo_lbl = QLabel()
        self.logo_lbl.setPixmap(make_logo(36))
        bl.addWidget(self.logo_lbl)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(lbl("Zenith", "h2"))
        self.crumb = lbl("Home", "sub")
        col.addWidget(self.crumb)
        bl.addLayout(col)
        bl.addStretch()
        self.update_btn = GlassButton("Update available", "accent", "download", height=40)
        self.update_btn.clicked.connect(self.open_update_overlay)
        self.update_btn.hide()
        bl.addWidget(self.update_btn)
        self.acct = GlassButton("", "normal", "user", height=42)
        self.acct.clicked.connect(self.open_account)
        bl.addWidget(self.acct)
        return bar

    def build_sidebar(self):
        side = Glass(28)
        side.setFixedWidth(84)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(8, 12, 8, 12)
        sl.setSpacing(6)
        self.group = QButtonGroup(self)
        self.names = ["Home", "Versions", "Mods", "Servers", "Profile", "Themes", "Settings"]
        self.nav = []
        icons = ["home", "versions", "mods", "servers", "user", "theme", "settings"]
        for i, (ic, nm) in enumerate(zip(icons, self.names)):
            b = NavButton(ic, nm)
            self.group.addButton(b, i)
            self.nav.append(b)
            if i == 5:
                sl.addStretch()
            sl.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        self.nav[0].setChecked(True)
        self.group.idClicked.connect(self.go)
        return side

    def build_footer(self):
        foot = Glass(20)
        foot.setFixedHeight(46)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(18, 0, 18, 0)
        self.status_lbl = lbl("Ready", "sub")
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(300)
        self.pbar.setTextVisible(False)
        self.pbar.hide()
        fl.addWidget(self.status_lbl)
        fl.addStretch()
        fl.addWidget(self.pbar)
        fl.addWidget(lbl(f"v{APP_VERSION}", "sub"))
        return foot

    # ---------------- plumbing
    def ui(self, fn):
        self.ui_call.emit(fn)

    def toast(self, text, kind="ok"):
        self.toaster.show_msg(text, kind)

    def status(self, t):
        self.ui(lambda: self.status_lbl.setText(t))

    def progress(self, v, mx):
        def f():
            self.pbar.setRange(0, max(mx, 1))
            self.pbar.setValue(v)
        self.ui(f)

    def set_busy(self, busy):
        self.busy = busy
        self.pbar.setVisible(busy)
        if busy:
            self.pbar.setRange(0, 0)
        self.home.launch.setEnabled(not busy)

    def go(self, i):
        self.nav[i].setChecked(True)
        self.stack.go(i)
        self.crumb.setText(self.names[i])
        if i == 2:
            self.mods.refresh_profiles()
            self.mods.refresh()
        elif i == 3:
            self.servers_page.refresh()

    # ---------------- account / settings
    def refresh_account(self):
        self.acct.setText(self.settings["username"])
        self.acct.setFixedWidth(max(110, self.acct.fontMetrics().horizontalAdvance(self.settings["username"]) + 74))
        self.home.refresh()

    def save_username(self, name):
        old_name = self.settings.get("username", "Player")
        names = self.settings.get("offline_accounts", [])
        if not isinstance(names, list):
            names = []
        if old_name not in names:
            names.append(old_name)
        if name not in names:
            names.append(name)
        self.settings["offline_accounts"] = [n for n in names if isinstance(n, str) and NAME_RE.match(n)]
        self.settings["username"] = name
        # Load this account's saved local cosmetics without sharing them with other names.
        all_cosmetics = self.settings.get("cosmetics_by_account", {})
        account_cosmetics = all_cosmetics.get(name, {}) if isinstance(all_cosmetics, dict) else {}
        if isinstance(account_cosmetics, dict) and account_cosmetics:
            self.settings["cosmetic_skin"] = account_cosmetics.get("skin", "")
            self.settings["cosmetic_capes"] = account_cosmetics.get("capes", ["", "", ""])
        save_json(SETTINGS_FILE, self.settings)
        self.refresh_account()
        self.settings_page.account.refresh()
        if hasattr(self, "profile_page"):
            self.profile_page.load_saved()
        self.toast("Offline account selected")

    def apply_settings(self, vals):
        self.settings.update(vals)
        save_json(SETTINGS_FILE, self.settings)
        self.toast("Settings saved")

    def apply_theme(self, name=None, glass=None, anim=None, smooth=None, save=True, toast=False):
        s = self.settings
        if name is not None:
            s["theme"] = name
        if glass is not None:
            s["glass"] = int(glass)
        if anim is not None:
            s["anim_bg"] = bool(anim)
        if smooth is not None:
            s["smooth"] = bool(smooth)
        THEME.set(s["theme"], s["glass"])
        THEME.smooth = bool(s["smooth"])
        QApplication.instance().setStyleSheet(build_qss())
        self.bg.animate = bool(s["anim_bg"])
        self.setWindowIcon(QIcon(make_logo(128)))
        self.logo_lbl.setPixmap(make_logo(36))
        self.home.hero.refresh()
        self.themes.sync()
        for w in self.findChildren(QWidget):
            w.update()
        if save:
            save_json(SETTINGS_FILE, s)
            if name is not None or toast:
                self.toast("Theme saved")

    def choose_background(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose background image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not f:
            return
        dest = HOME / ("background" + Path(f).suffix.lower())
        shutil.copy(f, dest)
        self.settings["bg_image"] = str(dest)
        save_json(SETTINGS_FILE, self.settings)
        self.bg.set_image(str(dest))
        self.toast("Background saved")

    def remove_background(self):
        self.settings["bg_image"] = ""
        save_json(SETTINGS_FILE, self.settings)
        self.bg.set_image("")
        self.toast("Background removed")

    # ---------------- overlays
    def open_overlay(self, card, width=560):
        self.close_overlay(True)
        self.overlay = Overlay(self.bg, card, width)
        return self.overlay

    def close_overlay(self, immediate=False):
        if self.overlay is not None:
            try:
                self.overlay.close_overlay(immediate)
            except RuntimeError:
                pass
            self.overlay = None

    def overlay_card(self, title, sub=None):
        card = Glass(30, solid=True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(26, 22, 26, 24)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.addLayout(page_title(title, sub))
        head.addStretch()
        x = icon_button("close", 40, "ghost", "Close")
        x.clicked.connect(lambda: self.close_overlay())
        head.addWidget(x, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)
        return card, lay

    def open_account(self):
        card, lay = self.overlay_card("Offline account", "Choose the name you play with")
        form = AccountForm(self)
        lay.addWidget(form)
        self.open_overlay(card, 560)
        form.edit.setFocus()
        form.edit.selectAll()

    def open_add_server(self):
        card, lay = self.overlay_card("Add Server", "Name and address of the server")
        name = QLineEdit()
        name.setPlaceholderText("Name  (example: My Server)")
        addr = QLineEdit()
        addr.setPlaceholderText("Address  (example: play.example.com or ip:25565)")
        lay.addWidget(name)
        lay.addWidget(addr)
        save = GlassButton("Save Server", "accent", "check", height=46)

        def do():
            n, a = name.text().strip(), addr.text().strip()
            if not n or not a:
                self.toast("Type a name and an address", "err")
                return
            self.servers.append({"name": n, "address": a})
            save_json(SERVERS_FILE, self.servers)
            self.servers_page.refresh()
            self.close_overlay()
            self.toast("Server saved")
        save.clicked.connect(do)
        addr.returnPressed.connect(do)
        lay.addWidget(save)
        self.open_overlay(card, 520)
        name.setFocus()

    def remove_server(self, i):
        if 0 <= i < len(self.servers):
            self.servers.pop(i)
            save_json(SERVERS_FILE, self.servers)
            self.servers_page.refresh()
            self.toast("Server removed")

    def open_delete_profile(self):
        p = self.get_active()
        if not p:
            return
        card, lay = self.overlay_card("Delete profile?", f"'{p['name']}' will be removed from the list.")
        lay.addWidget(lbl("Your world and mod files stay on disk in the profile folder.", "sub", True))
        row = QHBoxLayout()
        row.setSpacing(10)
        c = GlassButton("Cancel", "normal", height=44)
        c.clicked.connect(lambda: self.close_overlay())
        d = GlassButton("Delete", "danger", "trash", height=44)

        def do():
            self.profiles.pop(self.active)
            self.refresh_profiles()
            self.close_overlay()
            self.toast("Profile deleted")
        d.clicked.connect(do)
        row.addWidget(c)
        row.addWidget(d)
        lay.addLayout(row)
        self.open_overlay(card, 480)

    def open_edit_profile(self):
        p = self.get_active()
        if not p:
            return
        card, lay = self.overlay_card("Edit profile", f"{p['loader']}  ·  Minecraft {p['mc']}")
        name = QLineEdit(p["name"])
        lay.addWidget(lbl("Name", "h2"))
        lay.addWidget(name)
        lay.addWidget(lbl("Folder", "h2"))
        lay.addWidget(lbl(game_dir(p), "sub", True))
        row = QHBoxLayout()
        row.setSpacing(10)
        of = GlassButton("Open folder", "normal", "folder", height=44)
        of.clicked.connect(self.open_profile_folder)
        sv = GlassButton("Save", "accent", "check", height=44)

        def do():
            n = name.text().strip()
            if not n:
                self.toast("Name can't be empty", "err")
                return
            p["name"] = n
            self.refresh_profiles()
            self.close_overlay()
            self.toast("Profile saved")
        sv.clicked.connect(do)
        name.returnPressed.connect(do)
        row.addWidget(of)
        row.addWidget(sv)
        lay.addLayout(row)
        self.open_overlay(card, 520)
        name.setFocus()
        name.selectAll()

    def open_new_profile(self):
        card, lay = self.overlay_card("Create New Profile", "Pick how you want to start")
        stack = QStackedWidget()
        # --- menu
        menu = QWidget()
        ml = QVBoxLayout(menu)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(12)
        ml.addWidget(lbl("Already know what you want to play?", "h2"))
        q = QLineEdit()
        q.setPlaceholderText("Search mods and modpacks...")
        ml.addWidget(q)
        grid = QGridLayout()
        grid.setSpacing(12)
        opts = [("wand", "Wizard", "Create a profile from scratch in a few clicks"),
                ("download", "Install Modpack", "Browse modpacks and install one"),
                ("folder", "Import from File", "Choose a .mrpack or .zip modpack"),
                ("swap", "From other Launchers", "Migrate Prism / MultiMC instances")]
        cards = []
        for i, (ic, t, d) in enumerate(opts):
            c = OptionCard(ic, t, d)
            cards.append(c)
            grid.addWidget(c, i // 2, i % 2)
        ml.addLayout(grid)
        stack.addWidget(menu)
        # --- wizard
        wiz = QWidget()
        wl = QVBoxLayout(wiz)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)
        wname = QLineEdit()
        wname.setPlaceholderText("Profile name")
        rel = [v["id"] for v in self.all_versions if v["type"] == "release"] or ["1.21.1"]
        wver = QComboBox()
        wver.addItems(rel)
        wl.addWidget(lbl("Name", "h2"))
        wl.addWidget(wname)
        wl.addWidget(lbl("Minecraft version", "h2"))
        wl.addWidget(wver)
        wl.addWidget(lbl("Loader", "h2"))
        wload = {"v": "Vanilla"}
        lrow, lgrp, lb = segmented(LOADERS, lambda i: wload.__setitem__("v", LOADERS[i]))
        wl.addLayout(lrow)
        wiso = Switch(True)
        wl.addWidget(setting_row("Isolated profile", "Own worlds and mods", wiso))
        brow = QHBoxLayout()
        back = GlassButton("Back", "normal", height=44)
        create = GlassButton("Create Profile", "accent", "check", height=44)
        brow.addWidget(back)
        brow.addWidget(create, 1)
        wl.addLayout(brow)
        stack.addWidget(wiz)
        # --- launchers
        lp = QWidget()
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        inst_list = QVBoxLayout()
        inst_list.setSpacing(8)
        ll.addLayout(inst_list)
        brow2 = QHBoxLayout()
        back2 = GlassButton("Back", "normal", height=44)
        choose = GlassButton("Choose folder...", "normal", "folder", height=44)
        brow2.addWidget(back2)
        brow2.addWidget(choose, 1)
        ll.addLayout(brow2)
        stack.addWidget(lp)
        lay.addWidget(stack)

        def fit():
            for i in range(stack.count()):
                pg = stack.widget(i)
                pg.setSizePolicy(QSizePolicy.Policy.Preferred if i == stack.currentIndex() else QSizePolicy.Policy.Ignored,
                                 QSizePolicy.Policy.Preferred if i == stack.currentIndex() else QSizePolicy.Policy.Ignored)
            if self.overlay:
                self.overlay.relayout()

        def show(i):
            stack.setCurrentIndex(i)
            fit()
        fit()

        def do_create():
            n = wname.text().strip() or f"{wload['v']} {wver.currentText()}"
            prof = self.make_profile(n, wver.currentText(), wload["v"], wiso.isChecked())
            self.add_profile(prof)
            self.close_overlay()
            self.toast("Profile created")
        create.clicked.connect(do_create)
        back.clicked.connect(lambda: show(0))
        back2.clicked.connect(lambda: show(0))

        def import_file():
            f, _ = QFileDialog.getOpenFileName(self, "Select modpack", "", "Modpacks (*.mrpack *.zip)")
            if f:
                self.close_overlay()
                self.start_import(Path(f))

        def pick_launcher():
            clear_layout(inst_list)
            found = scan_launcher_instances()
            if not found:
                inst_list.addWidget(lbl("No Prism / MultiMC instances found automatically. Use Choose folder.", "sub", True))
            for inf in found[:8]:
                b = GlassButton(f"{inf['name']}   ·   {inf['loader']} {inf['mc'] or '?'}   ({inf['launcher']})",
                                "normal", "download", height=44, align="left")
                b.clicked.connect(lambda _, i=inf: (self.close_overlay(), self.start_import_instance(i)))
                inst_list.addWidget(b)
            show(2)

        def choose_folder():
            d = QFileDialog.getExistingDirectory(self, "Choose instance or .minecraft folder")
            if d:
                self.close_overlay()
                self.start_import_instance(instance_from_folder(Path(d)))

        choose.clicked.connect(choose_folder)
        cards[0].clicked.connect(lambda: (show(1), wname.setFocus()))
        cards[1].clicked.connect(lambda: (self.close_overlay(), self.go(2), self.mods.set_mode(2)))
        cards[2].clicked.connect(import_file)
        cards[3].clicked.connect(pick_launcher)

        def search():
            t = q.text().strip()
            if t:
                self.close_overlay()
                self.go(2)
                self.mods.query.setText(t)
                self.mods.set_mode(1)
        q.returnPressed.connect(search)
        self.open_overlay(card, 640)

    # ---------------- profiles
    def get_active(self):
        if 0 <= self.active < len(self.profiles):
            return self.profiles[self.active]
        return None

    def set_active(self, i):
        if i >= 0 and i != self.active:
            self.active = i
            self.refresh_profiles(sync_list=False)

    def refresh_profiles(self, sync_list=True):
        if self.profiles:
            self.active = min(max(self.active, 0), len(self.profiles) - 1)
        else:
            self.active = -1
        save_json(PROFILES_FILE, self.profiles)
        if sync_list:
            self.home.refresh()
        else:
            p = self.get_active()
            self.home.launch.setSub(f"{p['name']}  ·  {p['loader']} {p['mc']}" if p else "No profile - create one first")
        self.mods.refresh_profiles()

    def add_profile(self, prof):
        self.profiles.append(prof)
        self.active = len(self.profiles) - 1
        self.refresh_profiles()

    def make_profile(self, name, mc, loader, isolated=True):
        d = PROFILES_DIR / safe_name(name)
        n = 2
        while d.exists():
            d = PROFILES_DIR / f"{safe_name(name)}_{n}"
            n += 1
        d.mkdir(parents=True, exist_ok=True)
        return {"name": name, "mc": mc, "loader": loader, "dir": str(d), "isolated": isolated}

    def open_profile_folder(self):
        p = self.get_active()
        if p:
            open_path(game_dir(p))

    def create_from_selection(self, vp):
        if not vp.sel:
            self.toast("Select a version first", "err")
            return None
        loader = vp.loader
        for i, p in enumerate(self.profiles):
            if p["mc"] == vp.sel and p["loader"] == loader and p.get("isolated", True) == vp.iso.isChecked():
                self.active = i
                self.refresh_profiles()
                self.toast("Profile already exists - selected it")
                return p
        prof = self.make_profile(f"{loader} {vp.sel}", vp.sel, loader, vp.iso.isChecked())
        self.add_profile(prof)
        self.toast("Profile created")
        return prof

    def launch_selection(self, vp):
        p = self.create_from_selection(vp)
        if p:
            self.start_launch(p)

    # ---------------- versions
    def fetch_versions(self):
        try:
            vers = mll.utils.get_version_list()
        except Exception:
            vers = [{"id": v["id"], "type": v.get("type", "release"), "releaseTime": ""}
                    for v in mll.utils.get_installed_versions(str(MC_DIR))]
            if not vers:
                self.ui(lambda: self.toast("Could not load versions. Check your internet.", "err"))
        self.ui(lambda: self.on_versions(vers))

    def on_versions(self, vers):
        self.all_versions = vers
        rel = [v["id"] for v in vers if v["type"] == "release"]
        if not self.profiles and rel:
            self.profiles.append(self.make_profile("Latest Release", rel[0], "Vanilla"))
            self.active = 0
            self.refresh_profiles()
        self.versions.render()
        self.versions.select_default()

    # ---------------- importing
    def start_import(self, path):
        self.set_busy(True)
        self.status("Importing modpack...")

        def work():
            try:
                prof = self.import_pack(path)
                self.ui(lambda: (self.add_profile(prof), self.toast(f"Imported {prof['name']}")))
            except Exception as ex:
                self.ui(lambda: self.toast(f"Import failed: {ex}", "err"))
            finally:
                self.ui(lambda: (self.set_busy(False), self.status_lbl.setText("Ready")))
        threading.Thread(target=work, daemon=True).start()

    def start_import_instance(self, inf):
        self.set_busy(True)
        self.status(f"Copying {inf['name']}...")

        def work():
            try:
                latest = next((v["id"] for v in self.all_versions if v["type"] == "release"), "1.21.1")
                prof = self.make_profile(inf["name"], inf["mc"] or latest, inf["loader"])
                src = Path(inf["game"])
                shutil.copytree(src, prof["dir"], dirs_exist_ok=True)
                note = "" if inf["mc"] else " (version unknown, set to latest)"
                self.ui(lambda: (self.add_profile(prof), self.toast(f"Imported {prof['name']}{note}")))
            except Exception as ex:
                self.ui(lambda: self.toast(f"Import failed: {ex}", "err"))
            finally:
                self.ui(lambda: (self.set_busy(False), self.status_lbl.setText("Ready")))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _extract(z, member, base, rel):
        target = (base / rel).resolve()
        if not str(target).startswith(str(base.resolve())):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(member) as src, open(target, "wb") as out:
            out.write(src.read())

    def import_pack(self, path, name_hint=None):
        latest = next((v["id"] for v in self.all_versions if v["type"] == "release"), "1.21.1")
        name = name_hint or path.stem
        mc, loader = None, "Vanilla"
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "modrinth.index.json" in names:
                idx = json.loads(z.read("modrinth.index.json"))
                deps = idx.get("dependencies", {})
                if "neoforge" in deps:
                    raise Exception("NeoForge modpacks are not supported yet.")
                mc = deps.get("minecraft")
                for key, l in (("fabric-loader", "Fabric"), ("quilt-loader", "Quilt"), ("forge", "Forge")):
                    if key in deps:
                        loader = l
                name = name_hint or idx.get("name", name)
                prof = self.make_profile(name, mc or latest, loader)
                pdir = Path(prof["dir"])
                files = idx.get("files", [])
                for i, f in enumerate(files):
                    if f.get("env", {}).get("client") == "unsupported":
                        continue
                    self.status(f"Downloading pack files {i + 1}/{len(files)}")
                    self.progress(i + 1, len(files))
                    dest = (pdir / f["path"]).resolve()
                    if not str(dest).startswith(str(pdir.resolve())):
                        continue
                    download(f["downloads"][0], dest)
                for n in names:
                    for pre in ("overrides/", "client-overrides/"):
                        if n.startswith(pre) and not n.endswith("/"):
                            self._extract(z, n, pdir, n[len(pre):])
                return prof
            mmc = next((n for n in names if n.endswith("mmc-pack.json")), None)
            if mmc:
                mc, loader = parse_mmc(json.loads(z.read(mmc)).get("components", []))
            prof = self.make_profile(name, mc or latest, loader)
            pdir = Path(prof["dir"])
            root = ""
            for n in names:
                for seg in (".minecraft/", "minecraft/"):
                    i = n.find(seg)
                    if (i == 0 or (i > 0 and n[i - 1] == "/")) and n[:i].count("/") <= 1:
                        root = n[:i + len(seg)]
                        break
                if root:
                    break
            members = [n for n in names if not n.endswith("/")]
            if root:
                for n in members:
                    if n.startswith(root):
                        self._extract(z, n, pdir, n[len(root):])
            else:
                has_dirs = any(n.split("/")[0] in ("mods", "config", "saves", "resourcepacks", "shaderpacks") for n in members)
                only_jars = members and all(n.lower().endswith(".jar") for n in members)
                for n in members:
                    if not has_dirs and only_jars:
                        self._extract(z, n, pdir, "mods/" + os.path.basename(n))
                    else:
                        self._extract(z, n, pdir, n)
            if not mc:
                self.ui(lambda: self.toast(f"Version not found in the zip, using {latest}.", "err"))
            return prof

    # ---------------- mods / modpacks (Modrinth)
    def install_project(self, pid, title, kind):
        p = self.get_active()
        if kind == "mod":
            if not p:
                self.toast("Select a profile first", "err")
                return
            if p["loader"] == "Vanilla":
                self.toast("Vanilla profiles can't use mods. Use Fabric, Quilt or Forge.", "err")
                return
        self.set_busy(True)
        self.status(f"Installing {title}...")

        def work():
            try:
                if kind == "mod":
                    n = self.install_mod(dict(p), pid, set(), 0)
                    self.ui(lambda: self.toast(f"Installed {title}" + (f" (+{n - 1} required)" if n > 1 else "")))
                    self.ui(lambda: self.mods.mode == 0 and self.mods.refresh())
                else:
                    r = requests.get(f"{MODRINTH}/project/{pid}/version", headers=UA, timeout=20)
                    r.raise_for_status()
                    vers = r.json()
                    if not vers:
                        raise Exception("This modpack has no files.")
                    files = vers[0]["files"]
                    f = next((x for x in files if x.get("primary")), files[0])
                    tmp = CACHE_DIR / "packs" / f["filename"]
                    download(f["url"], tmp)
                    prof = self.import_pack(tmp, title)
                    self.ui(lambda: (self.add_profile(prof), self.toast(f"Installed modpack {title}")))
            except Exception as ex:
                self.ui(lambda: self.toast(f"Install failed: {ex}", "err"))
            finally:
                self.ui(lambda: (self.set_busy(False), self.status_lbl.setText("Ready")))
        threading.Thread(target=work, daemon=True).start()

    def install_mod(self, p, pid, seen, depth):
        if pid in seen or depth > 2:
            return 0
        seen.add(pid)
        r = requests.get(f"{MODRINTH}/project/{pid}/version", headers=UA, timeout=20,
                         params={"loaders": json.dumps([p["loader"].lower()]), "game_versions": json.dumps([p["mc"]])})
        r.raise_for_status()
        vers = r.json()
        if not vers:
            if depth == 0:
                raise Exception(f"No {p['loader']} build for Minecraft {p['mc']}.")
            return 0
        v = vers[0]
        files = v["files"]
        f = next((x for x in files if x.get("primary")), files[0])
        download(f["url"], Path(game_dir(p)) / "mods" / f["filename"])
        count = 1
        for dep in v.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                try:
                    count += self.install_mod(p, dep["project_id"], seen, depth + 1)
                except Exception:
                    pass
        return count

    # ---------------- servers
    def fetch_server_status(self, addr):
        try:
            r = requests.get(f"https://api.mcsrvstat.us/3/{addr}", headers=UA, timeout=12)
            j = r.json()
            res = {"online": bool(j.get("online")), "players": j.get("players", {}),
                   "motd": " ".join(j.get("motd", {}).get("clean", [])), "icon": j.get("icon")}
        except Exception:
            res = {"online": None}
        self.ui(lambda: self.servers_page.apply_status(addr, res))

    # ---------------- updates
    def check_update(self, manual=False):
        repo = self.settings["update_repo"].strip()
        if not repo:
            if manual:
                self.toast("Type your GitHub repo first (Settings > Updates)", "err")
            return
        if manual:
            self.toast("Checking for updates...")

        def work():
            try:
                r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest", headers=UA, timeout=15)
                if r.status_code == 404:
                    raise Exception("No release found. Is the repo public and has a release?")
                r.raise_for_status()
                j = r.json()
                tag = j.get("tag_name", "0")
                asset = next((a for a in j.get("assets", []) if a["name"].lower().endswith(".exe")), None)
                if parse_version(tag) > parse_version(APP_VERSION):
                    info = {"tag": tag, "url": asset["browser_download_url"] if asset else None,
                            "body": (j.get("body") or "")[:400], "page": j.get("html_url")}
                    self.ui(lambda: self.on_update_found(info))
                elif manual:
                    self.ui(lambda: self.toast(f"You are up to date (v{APP_VERSION})"))
            except Exception as ex:
                if manual:
                    self.ui(lambda: self.toast(f"Update check failed: {ex}", "err"))
        threading.Thread(target=work, daemon=True).start()

    def on_update_found(self, info):
        self.update_info = info
        self.update_btn.setText(f"Update {info['tag']}")
        self.update_btn.setFixedWidth(self.update_btn.fontMetrics().horizontalAdvance(self.update_btn.text()) + 80)
        self.update_btn.show()
        self.toast(f"New version {info['tag']} is available")

    def open_update_overlay(self):
        info = self.update_info
        if not info:
            return
        card, lay = self.overlay_card(f"Update {info['tag']}", f"You have v{APP_VERSION}")
        if info["body"]:
            lay.addWidget(lbl(info["body"], "sub", True))
        self.up_bar = QProgressBar()
        self.up_bar.hide()
        lay.addWidget(self.up_bar)
        btn = GlassButton("Update now", "accent", "download", height=48)
        btn.clicked.connect(lambda: self.do_update(btn))
        lay.addWidget(btn)
        self.open_overlay(card, 520)

    def do_update(self, btn):
        info = self.update_info
        if not getattr(sys, "frozen", False):
            self.toast("Auto-update works in the built .exe. Opening the release page.", "err")
            if info.get("page"):
                QDesktopServices.openUrl(QUrl(info["page"]))
            return
        if not info.get("url"):
            self.toast("This release has no .exe file attached", "err")
            return

        btn.setEnabled(False)
        btn.setText("Downloading...")
        self.up_bar.show()

        def work():
            try:
                new = Path(tempfile.gettempdir()) / "ZenithLauncher_new.exe"

                def prog(done, total):
                    self.ui(lambda: (self.up_bar.setRange(0, max(1, total)),
                                     self.up_bar.setValue(done)))

                if new.exists():
                    new.unlink()
                download(info["url"], new, prog)
                if not new.exists() or new.stat().st_size < 100_000:
                    raise Exception("Downloaded EXE is missing or unexpectedly small.")

                cur = Path(sys.executable).resolve()
                old = cur.with_name(cur.name + ".old")
                bat = Path(tempfile.gettempdir()) / "zenith_updater.bat"
                log = Path(tempfile.gettempdir()) / "ZenithLauncher_update.log"
                script = (
                    "@echo off\r\n"
                    "setlocal\r\n"
                    f'set "NEW={new}"\r\n'
                    f'set "CUR={cur}"\r\n'
                    f'set "OLD={old}"\r\n'
                    f'set "LOG={log}"\r\n'
                    'echo Zenith Launcher updater started > "%LOG%"\r\n'
                    'set /a tries=0\r\n'
                    ':retry\r\n'
                    'timeout /t 1 /nobreak >> "%LOG%" 2>&1\r\n'
                    'set /a tries+=1\r\n'
                    'if exist "%CUR%" move /y "%CUR%" "%OLD%" >> "%LOG%" 2>&1\r\n'
                    'if exist "%CUR%" goto failed_attempt\r\n'
                    'move /y "%NEW%" "%CUR%" >> "%LOG%" 2>&1\r\n'
                    'if errorlevel 1 goto restore_old\r\n'
                    'if not exist "%CUR%" goto restore_old\r\n'
                    'echo Update installed successfully >> "%LOG%"\r\n'
                    'start "" "%CUR%"\r\n'
                    'exit /b 0\r\n'
                    ':restore_old\r\n'
                    'if exist "%OLD%" if not exist "%CUR%" move /y "%OLD%" "%CUR%" >> "%LOG%" 2>&1\r\n'
                    ':failed_attempt\r\n'
                    'if %tries% lss 40 goto retry\r\n'
                    'echo UPDATE FAILED after retries. Check permissions and log above. >> "%LOG%"\r\n'
                    'exit /b 1\r\n'
                )
                bat.write_text(script, encoding="utf-8", newline="")
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith("_PYI") and k != "_MEIPASS2"}
                env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
                subprocess.Popen(["cmd", "/c", str(bat)], env=env, close_fds=True,
                                 creationflags=0x08000000 | 0x00000200)
                self.ui(QApplication.quit)
            except Exception as ex:
                self.ui(lambda: (self.toast(f"Update failed: {ex}", "err"),
                                 btn.setEnabled(True), btn.setText("Update now")))
        threading.Thread(target=work, daemon=True).start()

    # ---------------- launching
    def start_launch(self, profile, server=None):
        if self.busy:
            return
        if not profile:
            self.toast("Create or select a profile first", "err")
            return
        self.set_busy(True)
        threading.Thread(target=self.launch_worker, args=(dict(profile), server), daemon=True).start()

    def java_component(self, vid):
        for _ in range(4):
            f = MC_DIR / "versions" / vid / f"{vid}.json"
            if not f.exists():
                return None
            j = json.loads(f.read_text(encoding="utf-8"))
            if "javaVersion" in j:
                return j["javaVersion"].get("component")
            vid = j.get("inheritsFrom")
            if not vid:
                return None
        return None

    def ensure_installed(self, mc, loader, cb):
        d = str(MC_DIR)
        if loader == "Vanilla":
            mll.install.install_minecraft_version(mc, d, callback=cb)
            return mc
        if loader in ("Fabric", "Quilt"):
            if loader == "Fabric":
                mll.fabric.install_fabric(mc, d, callback=cb)
                lv = mll.fabric.get_latest_loader_version()
                key, fallback = "fabric-loader", f"fabric-loader-{lv}-{mc}"
            else:
                mll.quilt.install_quilt(mc, d, callback=cb)
                lv = mll.quilt.get_latest_loader_version()
                key, fallback = "quilt-loader", f"quilt-loader-{lv}-{mc}"
            for v in mll.utils.get_installed_versions(d):
                if v["id"] == fallback:
                    return fallback
            for v in mll.utils.get_installed_versions(d):
                if key in v["id"] and v["id"].endswith(mc):
                    return v["id"]
            return fallback
        fv = mll.forge.find_forge_version(mc)
        if not fv:
            raise Exception(f"No Forge version found for Minecraft {mc}.")
        vid = mll.forge.forge_to_installed_version(fv)
        if not (MC_DIR / "versions" / vid).exists():
            mll.install.install_minecraft_version(mc, d, callback=cb)
            java = None
            comp = self.java_component(mc)
            if comp:
                try:
                    mll.runtime.install_jvm_runtime(comp, d, callback=cb)
                    java = mll.runtime.get_executable_path(comp, d)
                except Exception:
                    java = None
            mll.forge.install_forge_version(fv, d, callback=cb, java=java)
        return vid

    def launch_worker(self, p, server):
        try:
            state = {"max": 1}
            cb = {"setStatus": lambda t: self.status(t),
                  "setProgress": lambda v: self.progress(v, state["max"]),
                  "setMax": lambda m: state.__setitem__("max", m)}
            s = self.settings
            self.status(f"Preparing {p['loader']} {p['mc']}...")
            vid = self.ensure_installed(p["mc"], p["loader"], cb)
            gdir = game_dir(p)
            opts = {
                "username": s["username"],
                "uuid": str(uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + s["username"])),
                "token": "0",
                "launcherName": "ZenithLauncher", "launcherVersion": APP_VERSION,
                "gameDirectory": gdir,
                "jvmArguments": [f"-Xmx{s['memory']}M", "-Xms512M"] + s["jvm_args"].split(),
                "customResolution": True,
                "resolutionWidth": str(s["width"]), "resolutionHeight": str(s["height"]),
            }
            if s["java_path"]:
                opts["executablePath"] = s["java_path"]
            else:
                comp = self.java_component(vid)
                if comp:
                    try:
                        mll.runtime.install_jvm_runtime(comp, str(MC_DIR), callback=cb)
                        exe = mll.runtime.get_executable_path(comp, str(MC_DIR))
                        if exe:
                            opts["executablePath"] = exe
                    except Exception:
                        pass
            if server:
                host, _, port = server.partition(":")
                opts["server"] = host
                if port:
                    opts["port"] = port
            cmd = mll.command.get_minecraft_command(vid, str(MC_DIR), opts)
            if s["fullscreen"]:
                cmd.append("--fullscreen")
            Path(gdir).mkdir(parents=True, exist_ok=True)
            self.status("Launching game...")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            log = open(LOG_FILE, "wb")
            proc = subprocess.Popen(cmd, cwd=gdir, creationflags=flags, stdout=log, stderr=subprocess.STDOUT)
            self.status("Game started")
            self.ui(lambda: self.toast("Game started - have fun!"))
            self.ui(lambda: self.set_busy(False))
            code = proc.wait()
            log.close()
            if code != 0:
                self.ui(lambda: self.toast(f"Game closed with code {code}. See Settings > Storage > launch log.", "err"))
            self.status("Ready")
        except Exception as ex:
            self.ui(lambda: self.toast(f"Launch failed: {ex}", "err"))
            self.ui(lambda: (self.set_busy(False), self.status_lbl.setText("Ready")))


# ------------------------------------------------------------------ launcher migration helpers
def parse_mmc(components):
    mc, loader = None, "Vanilla"
    for c in components:
        uid, ver = c.get("uid"), c.get("version")
        if uid == "net.minecraft":
            mc = ver
        elif uid == "net.fabricmc.fabric-loader":
            loader = "Fabric"
        elif uid == "org.quiltmc.quilt-loader":
            loader = "Quilt"
        elif uid == "net.minecraftforge":
            loader = "Forge"
        elif uid == "net.neoforged":
            raise Exception("NeoForge instances are not supported yet.")
    return mc, loader


def instance_from_folder(d):
    mc, loader = None, "Vanilla"
    mmc = d / "mmc-pack.json"
    if mmc.exists():
        try:
            mc, loader = parse_mmc(json.loads(mmc.read_text(encoding="utf-8")).get("components", []))
        except Exception:
            pass
    game = d
    for sub in ("minecraft", ".minecraft"):
        if (d / sub).is_dir():
            game = d / sub
            break
    return {"name": d.name, "mc": mc, "loader": loader, "game": str(game), "launcher": "folder"}


def scan_launcher_instances():
    roots = []
    appdata = os.environ.get("APPDATA")
    home = Path.home()
    if appdata:
        roots += [(Path(appdata) / "PrismLauncher" / "instances", "Prism"), (Path(appdata) / "MultiMC" / "instances", "MultiMC")]
    roots += [(home / ".local/share/PrismLauncher/instances", "Prism"), (home / "MultiMC/instances", "MultiMC")]
    out = []
    for root, label in roots:
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "mmc-pack.json").exists():
                    try:
                        inf = instance_from_folder(d)
                        inf["launcher"] = label
                        out.append(inf)
                    except Exception:
                        pass
    return out


def excepthook(etype, value, tb):
    text = "".join(traceback.format_exception(etype, value, tb))
    try:
        ERR_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ERR_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    print(text, file=sys.stderr)


def main():
    global IMG
    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if "--make-icon" in sys.argv:
        make_logo(256).save("zenith.png")
        print("saved zenith.png")
        return
    HOME.mkdir(parents=True, exist_ok=True)
    IMG = ImageLoader()
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
