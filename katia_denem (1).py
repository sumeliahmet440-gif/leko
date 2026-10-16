# -*- coding: utf-8 -*-
"""
KATIA - Windows 10 sesli masaüstü asistanı (PyQt6 + Groq)

Kurulum:
    pip install PyQt6 requests psutil pyttsx3 groq ddgs SpeechRecognition pyaudio pyautogui

Groq anahtarı: AYARLAR penceresinden gir (katia_ayar.json'a kaydedilir)
veya GROQ_API_KEY ortam değişkenini tanımla.
"""
import sys
import os
import re
import json
import math
import time
import html
import queue
import random
import subprocess
import webbrowser
from datetime import datetime
from urllib.parse import quote, quote_plus

import requests
import psutil
import pyttsx3

try:
    import winsound
except ImportError:
    winsound = None

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QTextEdit, QTextBrowser, QGridLayout, QDialog,
    QFrame, QMessageBox, QFileDialog, QComboBox, QCheckBox, QSpinBox, QTabWidget
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, QRectF, QPointF, pyqtSignal
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QPen, QColor, QBrush, QRadialGradient,
    QShortcut, QKeySequence
)

# --- OPSİYONEL KÜTÜPHANELER ---
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    Groq = None
    GROQ_AVAILABLE = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    sr = None
    SR_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

from katia_cihaz import LedController, parse_led
from katia_web import WebServer, local_ip, FLASK_AVAILABLE as WEB_AVAILABLE

# --- GROQ API ANAHTARI ---
GROQ_API_KEY = "BURAYA_GROQ_API_KEY_YAZ"   # İstersen buraya yaz; AYARLAR'dan girmek daha rahat
PLACEHOLDER = "BURAYA_GROQ_API_KEY_YAZ"

# WhatsApp: mesaj açıldıktan sonra Enter'a otomatik bas (pyautogui gerekir)
WHATSAPP_AUTO_SEND = True
WHATSAPP_USE_WEB = False   # True: WhatsApp Web (tarayıcı), False: Masaüstü uygulaması

# --- TEMA ---
BG, TEXT, DIM = "#050403", "#e8dccb", "#7a7066"
ACCENT, PINK = "#c9a27a", "#ff3b6b"
LINE, LINE2 = "#1f1a16", "#2e2822"

GUNLER = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
AYLAR = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ",
         "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]


def tr_upper(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def tr_lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


# --- HAFIZA / AYAR DOSYALARI ---
MEMORY_DIR = "lekobilgi/asistan"
MEMORY_FILE = os.path.join(MEMORY_DIR, "katia_hafiza.json")
CONFIG_FILE = os.path.join(MEMORY_DIR, "katia_ayar.json")

DEFAULT_MEMORY = {
    "algoritma": "Bir problemi çözmek veya belirli bir amaca ulaşmak için takip edilen adım adım mantıksal yoldur.",
    "yazilim": "Bilgisayara ne yapacağını söyleyen dijital komutlar ve programlar bütünüdür."
}


def ensure_memory_path():
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if not os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MEMORY, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Hafıza dizin hatası: {e}")


ensure_memory_path()


def load_hafiza():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return DEFAULT_MEMORY


def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"groq_api_key": "", "contacts": {}}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ayar kaydedilemedi: {e}")


# --- KULLANICI TEMASI (AYARLAR > GÖRÜNÜM) ---
_T = load_config().get("theme", {})
BG = _T.get("BG", BG)
ACCENT = _T.get("ACCENT", ACCENT)
PINK = _T.get("PINK", PINK)

# --- ŞEHİR VE ADA VERİTABANI ---
CITIES_DATA = {
    "istanbul": {"detay": "Tarihi zenginliklerle dolu kentin kasvetli sokakları.", "gezilecek": "Ayasofya, Topkapı Sarayı, Kız Kulesi"},
    "ankara": {"detay": "Gri ve soğuk bürokrasi merkezi.", "gezilecek": "Anıtkabir, Ankara Kalesi"},
    "izmir": {"detay": "Ege kıyısındaki sıcak ve kuru yerleşim alanı.", "gezilecek": "Kordon, Efes Antik Kenti, Saat Kulesi"}
}

ISLANDS_DATA = {
    "bozcaada": {"detay": "Ege denizinin ortasında izole bir kara parçası.", "gezilecek": "Bozcaada Kalesi, Ayazma Plajı"},
    "büyükada": {"detay": "Prens Adaları'nın en büyük karantinası.", "gezilecek": "Aya Yorgi Manastırı"}
}

# --- SİTELER ---
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "github": "https://github.com",
    "instagram": "https://www.instagram.com", "twitter": "https://x.com",
    "facebook": "https://www.facebook.com", "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
    "whatsapp web": "https://web.whatsapp.com", "trendyol": "https://www.trendyol.com",
    "hepsiburada": "https://www.hepsiburada.com", "amazon": "https://www.amazon.com.tr",
    "sahibinden": "https://www.sahibinden.com", "reddit": "https://www.reddit.com",
    "twitch": "https://www.twitch.tv", "discord": "https://discord.com/app",
    "wikipedia": "https://tr.wikipedia.org", "vikipedi": "https://tr.wikipedia.org",
    "haritalar": "https://www.google.com/maps", "çeviri": "https://translate.google.com",
}

SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={}",
    "google": "https://www.google.com/search?q={}",
    "bing": "https://www.bing.com/search?q={}",
    "yandex": "https://yandex.com.tr/search/?text={}",
    "amazon": "https://www.amazon.com.tr/s?k={}",
    "trendyol": "https://www.trendyol.com/sr?q={}",
    "hepsiburada": "https://www.hepsiburada.com/ara?q={}",
    "sahibinden": "https://www.sahibinden.com/arama?query_text={}",
    "github": "https://github.com/search?q={}",
    "wikipedia": "https://tr.wikipedia.org/w/index.php?search={}",
    "vikipedi": "https://tr.wikipedia.org/w/index.php?search={}",
    "maps": "https://www.google.com/maps/search/{}",
    "harita": "https://www.google.com/maps/search/{}",
    "spotify": "https://open.spotify.com/search/{}",
    "twitter": "https://x.com/search?q={}",
    "reddit": "https://www.reddit.com/search/?q={}",
}

WMO = [
    ((0,), "açık", "☀"), ((1,), "çoğunlukla açık", "☀"), ((2,), "parçalı bulutlu", "⛅"),
    ((3,), "kapalı", "☁"), ((45, 48), "sisli", "☁"),
    ((51, 53, 55, 56, 57), "çiseleme", "☂"), ((61, 63, 65, 66, 67), "yağmurlu", "☂"),
    ((71, 73, 75, 77, 85, 86), "karlı", "❄"), ((80, 81, 82), "sağanak yağışlı", "☂"),
    ((95, 96, 99), "gök gürültülü fırtına", "⚡"),
]


def wmo_info(code):
    for codes, text, icon in WMO:
        if code in codes:
            return text, icon
    return "değişken", "☁"


# =====================================================================
#                          YARDIMCI İŞ PARÇACIKLARI
# =====================================================================
class Speaker(QThread):
    """Tek bir kalıcı iş parçacığında sırayla konuşur (üst üste binmez)."""
    speaking = pyqtSignal(bool)

    def __init__(self, cfg=None):
        super().__init__()
        self.cfg = cfg if cfg is not None else {}
        self.q = queue.Queue()

    def say(self, text):
        self.q.put(text)

    def stop(self):
        self.q.put(None)

    def run(self):
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            engine.setProperty("volume", 1.0)
            for v in engine.getProperty("voices"):
                blob = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()
                if any(k in blob for k in ("tr-tr", "tr_tr", "turk", "tolga", "filiz")):
                    engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            print(f"Ses motoru hatası: {e}")
        while True:
            text = self.q.get()
            if text is None:
                break
            if not engine:
                continue
            vc = self.cfg.get("voice", {})
            if not vc.get("on", True):
                continue
            try:
                engine.setProperty("rate", int(vc.get("rate", 165)))
                engine.setProperty("volume", int(vc.get("volume", 100)) / 100)
            except Exception:
                pass
            try:
                self.speaking.emit(True)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"Ses hatası: {e}")
            finally:
                self.speaking.emit(False)


class Worker(QThread):
    done = pyqtSignal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            res = self.fn(*self.args)
        except Exception as e:
            res = e
        self.done.emit(res)


# =====================================================================
#                           İNTERNET FONKSİYONLARI
# =====================================================================
def fetch_location_weather():
    loc = {"city": "İstanbul", "country": "Türkiye", "lat": 41.0, "lon": 28.983}
    try:
        r = requests.get("http://ip-api.com/json/?lang=tr&fields=status,country,city,lat,lon", timeout=5).json()
        if r.get("status") == "success":
            loc = {"city": r["city"], "country": r["country"], "lat": r["lat"], "lon": r["lon"]}
    except Exception:
        pass
    data = dict(loc)
    data.update(get_weather(loc["lat"], loc["lon"]))
    data["tile"] = get_tile(loc["lat"], loc["lon"])
    return data


def get_weather(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
           "&timezone=auto&forecast_days=1")
    j = requests.get(url, timeout=6).json()
    cond, icon = wmo_info(j["current"]["weather_code"])
    return {"temp": j["current"]["temperature_2m"], "cond": cond, "icon": icon,
            "tmax": j["daily"]["temperature_2m_max"][0], "tmin": j["daily"]["temperature_2m_min"][0]}


def get_tile(lat, lon, z=12):
    try:
        n = 2 ** z
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        r = requests.get(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                         headers={"User-Agent": "KatiaAssistant/1.0"}, timeout=5)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def city_weather_text(city):
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": city, "count": 1, "language": "tr"}, timeout=6).json()
    if not g.get("results"):
        return f"'{city}' diye bir yer bulamadım patron."
    r = g["results"][0]
    w = get_weather(r["latitude"], r["longitude"])
    return (f"{r['name']}: hava {w['cond']}, {round(w['temp'])} derece. "
            f"En düşük {round(w['tmin'])}, en yüksek {round(w['tmax'])}.")


def web_search(query, n=5):
    if DDGS is not None:
        try:
            with DDGS() as d:
                res = list(d.text(query, region="tr-tr", max_results=n))
            if res:
                return "\n".join(f"- {x.get('title', '')}: {x.get('body', '')} ({x.get('href', '')})" for x in res)
        except Exception:
            pass
    try:
        url = f"https://tr.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '_')}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("extract"):
            return res.json()["extract"]
    except Exception:
        pass
    return "Arama sonucu bulunamadı."


def fetch_page_text(url, limit=7000):
    if not url.startswith("http"):
        url = "https://" + url
    r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
    txt = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", r.text)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    return re.sub(r"\s+", " ", txt).strip()[:limit]


def normalize_phone(s):
    d = re.sub(r"\D", "", s or "")
    if d.startswith("00"):
        d = d[2:]
    elif d.startswith("0"):
        d = "90" + d[1:]
    elif len(d) == 10 and d.startswith("5"):
        d = "90" + d
    return d if len(d) >= 11 else None


# =====================================================================
#                              ÖZEL WIDGET'LAR
# =====================================================================
def mk_label(text, size=9, spacing=3, color=DIM, bold=False):
    lb = QLabel(text)
    f = QFont("Consolas", size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    lb.setFont(f)
    lb.setStyleSheet(f"color:{color}; background:transparent; border:none;")
    return lb


def flat_btn(text, color=DIM, size=9, border=True, bold=False):
    b = QPushButton(text)
    f = QFont("Consolas", size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
    b.setFont(f)
    bd = f"1px solid {LINE2}" if border else "none"
    b.setStyleSheet(
        f"QPushButton{{color:{color};background:transparent;border:{bd};border-radius:3px;padding:6px 10px;}}"
        f"QPushButton:hover{{color:{TEXT};border-color:{ACCENT};}}")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def sep():
    s = QFrame()
    s.setFixedHeight(1)
    s.setStyleSheet(f"background:{LINE}; border:none;")
    return s


class RingWidget(QWidget):
    def __init__(self, size, thick=3, color=ACCENT, main_size=16, sub_size=7):
        super().__init__()
        self.setFixedSize(size, size)
        self.thick, self.color, self.main_size, self.sub_size = thick, color, main_size, sub_size
        self.value = self.value2 = 0.0
        self.main = self.sub = ""
        self.setStyleSheet("background:transparent;")

    def set(self, value=0.0, main="", sub="", value2=0.0):
        self.value, self.main, self.sub, self.value2 = value, main, sub, value2
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        m = 10
        rect = QRectF(m, m, w - 2 * m, w - 2 * m)
        p.save()
        p.translate(w / 2, w / 2)
        p.setPen(QPen(QColor(201, 162, 122, 70), 1))
        r = w / 2 - 2
        for i in range(60):
            p.drawLine(QPointF(0, -r), QPointF(0, -(r - (5 if i % 5 == 0 else 2))))
            p.rotate(6)
        p.restore()
        p.setPen(QPen(QColor("#2a2420"), self.thick))
        p.drawEllipse(rect)
        if self.value > 0:
            pen = QPen(QColor(self.color), self.thick)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(min(self.value, 1) * 360 * 16))
        if self.value2 > 0:
            pen = QPen(QColor(PINK), 1.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect.adjusted(7, 7, -7, -7), 90 * 16, -int(min(self.value2, 1) * 360 * 16))
        p.setPen(QColor(TEXT))
        f = QFont("Consolas", self.main_size)
        f.setBold(True)
        p.setFont(f)
        if self.sub:
            p.drawText(QRectF(0, w * 0.25, w, w * 0.3), Qt.AlignmentFlag.AlignCenter, self.main)
            f2 = QFont("Consolas", self.sub_size)
            f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
            p.setFont(f2)
            p.setPen(QColor(DIM))
            p.drawText(QRectF(0, w * 0.55, w, w * 0.15), Qt.AlignmentFlag.AlignCenter, self.sub)
        else:
            p.drawText(QRectF(0, 0, w, w), Qt.AlignmentFlag.AlignCenter, self.main)


class OrbWidget(QWidget):
    clicked = pyqtSignal()
    PALETTE = {"idle": (201, 162, 122), "listen": (255, 59, 107),
               "think": (120, 160, 255), "speak": (255, 205, 140)}
    AMP = {"idle": 0.05, "listen": 0.18, "think": 0.12, "speak": 0.25}

    def __init__(self):
        super().__init__()
        self.state, self.phase = "idle", 0.0
        self.setMinimumHeight(300)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background:transparent;")
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def set_state(self, s):
        self.state = s

    def _tick(self):
        self.phase += 0.03 if self.state == "idle" else 0.06
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, g, b = self.PALETTE[self.state]
        cx, cy = self.width() / 2, self.height() / 2
        pulse = 1 + self.AMP[self.state] * math.sin(self.phase * 3)
        base = min(self.width(), self.height()) * 0.17 * pulse
        grad = QRadialGradient(QPointF(cx, cy), base * 2.4)
        grad.setColorAt(0, QColor(r, g, b, 150))
        grad.setColorAt(0.5, QColor(r, g, b, 40))
        grad.setColorAt(1, QColor(r, g, b, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), base * 2.4, base * 2.4)
        p.setBrush(QColor(200, 200, 200, 230))
        p.drawEllipse(QPointF(cx, cy), 12, 12)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for k in range(3):
            rad = 120 + k * 45
            p.setPen(QPen(QColor(r, g, b, 70 - k * 15), 2))
            start = int((self.phase * 25 * (k + 1)) % 360 * 16)
            p.drawArc(QRectF(cx - rad, cy - rad, rad * 2, rad * 2), start, 100 * 16)


class RangeBar(QWidget):
    def __init__(self):
        super().__init__()
        self.lo = self.hi = self.cur = 0
        self.setFixedHeight(14)

    def set(self, lo, hi, cur):
        self.lo, self.hi, self.cur = lo, hi, cur
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height() / 2
        p.setPen(QPen(QColor("#2a2420"), 2))
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        frac = (self.cur - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 1
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawEllipse(QPointF(max(4, min(self.width() - 4, frac * self.width())), y), 4, 4)


class MapWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(130)
        self.pix, self.coord = None, ""

    def set_data(self, tile_bytes, coord):
        self.coord = coord
        if tile_bytes:
            pm = QPixmap()
            pm.loadFromData(tile_bytes)
            self.pix = pm
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#0a0806"))
        if self.pix:
            sc = self.pix.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(0, -(sc.height() - h) // 2, sc)
        p.fillRect(0, 0, w, h, QColor(20, 10, 0, 175))
        p.setPen(QPen(QColor(ACCENT), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(w / 2, h / 2), 7, 7)
        p.drawEllipse(QPointF(w / 2, h / 2), 2, 2)
        p.setPen(QColor(ACCENT))
        p.setFont(QFont("Consolas", 8))
        p.drawText(QRectF(0, h - 22, w - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.coord)


# =====================================================================
#                                DİYALOGLAR
# =====================================================================
class AIModelsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI MODELLERİ")
        self.setFixedSize(650, 400)
        self.setStyleSheet("background-color: #0b0b0e; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        title_lbl = QLabel("AI MODELLERİ")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title_lbl)

        sub_lbl = QLabel("Takmak istediğin çipi seç.")
        sub_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        layout.addWidget(sub_lbl)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        models = [
            ("JARVIS", "Jarvis.py", "#0088ff"),
            ("FRIDAY", "Friday.py", "#ffaa00"),
            ("KATIA", "Katia.py", "#aa00ff"),
            ("ULTRON", "Ultron.py", "#ff0000")
        ]

        for name, script, color in models:
            card = QFrame()
            card.setFixedSize(120, 180)
            card.setStyleSheet(f"background-color: #141418; border: 2px solid {color}; border-radius: 10px;")
            card_layout = QVBoxLayout(card)

            lbl_name = QLabel(name)
            lbl_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            lbl_name.setStyleSheet(f"color: {color}; border: none;")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_select = QPushButton("SEÇ")
            btn_select.setStyleSheet(f"background-color: {color}; color: #000000; font-weight: bold; border-radius: 4px; padding: 5px;")
            btn_select.clicked.connect(lambda _, s=script: self.switch_model(s))

            card_layout.addWidget(lbl_name)
            card_layout.addStretch()
            card_layout.addWidget(btn_select)
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        slot_lbl = QLabel("─── TAKILI ───")
        slot_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slot_lbl.setStyleSheet("color: #ff5500; font-weight: bold; margin-top: 15px;")
        layout.addWidget(slot_lbl)

    def switch_model(self, script_name):
        if os.path.exists(script_name):
            subprocess.Popen([sys.executable, script_name])
            if self.parent():
                self.parent().close()
            self.close()
        else:
            print(f"{script_name} dosyası bulunamadı!")


class XOXDialog(QDialog):
    """3x3 (3 yan yana) ve 6x6 (4 yan yana) XOX oyunları tek sınıfta."""
    def __init__(self, parent=None, n=3, win=3):
        super().__init__(parent)
        self.n, self.win = n, win
        big = n == 6
        self.setWindowTitle("KATIA - DEVASA 6x6 XOX" if big else "KATIA - 3x3 XOX")
        cell = 70 if big else 90
        self.setFixedSize(500, 580) if big else self.setFixedSize(350, 420)
        self.setStyleSheet(f"background-color: {BG}; color: {ACCENT};")
        self.start_text = "6x6 ARENA - YAN YANA 4 YAPAN KAZANIR!" if big else "SIRA SENDE PATRON (X)"
        self.board = [""] * (n * n)
        self.turn = "X"

        layout = QVBoxLayout()
        self.info_label = QLabel(self.start_text)
        self.info_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)

        grid = QGridLayout()
        self.buttons = []
        for i in range(n * n):
            btn = QPushButton("")
            btn.setFont(QFont("Consolas", 14 if big else 22, QFont.Weight.Bold))
            btn.setFixedSize(cell, cell)
            btn.setStyleSheet(self.cell_style(ACCENT, "#3a2e22"))
            btn.clicked.connect(lambda _, idx=i: self.make_move(idx))
            grid.addWidget(btn, i // n, i % n)
            self.buttons.append(btn)
        layout.addLayout(grid)

        btn_layout = QHBoxLayout()
        self.restart_btn = QPushButton("YENİDEN OYNA")
        self.restart_btn.setStyleSheet("background-color: #3a2e22; color: #ffffff; font-weight: bold; padding: 6px;")
        self.restart_btn.clicked.connect(self.reset_board)
        self.restart_btn.hide()
        btn_layout.addWidget(self.restart_btn)
        close_btn = QPushButton("KAPAT")
        close_btn.setStyleSheet("background-color: #1f1a16; color: #c9a27a; font-weight: bold; padding: 6px;")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    @staticmethod
    def cell_style(color, border):
        return f"background-color: #0d0a08; color: {color}; border: 1px solid {border}; border-radius: 4px;"

    def check_win(self, p):
        n, k = self.n, self.win
        for r in range(n):
            for c in range(n):
                for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                    cells = [(r + dr * i, c + dc * i) for i in range(k)]
                    if all(0 <= a < n and 0 <= b < n and self.board[a * n + b] == p for a, b in cells):
                        return True
        return False

    def make_move(self, idx):
        if self.board[idx] == "" and self.turn == "X":
            self.board[idx] = "X"
            self.buttons[idx].setText("X")
            self.buttons[idx].setStyleSheet(self.cell_style("#00ffff", "#005555"))
            if self.check_win("X"):
                self.info_label.setText("KAZANDIN PATRON!")
                return self.end_game()
            if "" not in self.board:
                self.info_label.setText("BERABERE!")
                return self.end_game()
            self.turn = "O"
            self.info_label.setText("KATIA DÜŞÜNÜYOR...")
            QTimer.singleShot(300, self.ai_move)

    def ai_move(self):
        empty = [i for i, x in enumerate(self.board) if x == ""]
        if empty:
            move = random.choice(empty)
            self.board[move] = "O"
            self.buttons[move].setText("O")
            self.buttons[move].setStyleSheet(self.cell_style(PINK, PINK))
            if self.check_win("O"):
                self.info_label.setText("KATIA KAZANDI!")
                return self.end_game()
            if "" not in self.board:
                self.info_label.setText("BERABERE!")
                return self.end_game()
        self.turn = "X"
        self.info_label.setText("SIRA SENDE PATRON (X)")

    def end_game(self):
        for b in self.buttons:
            b.setEnabled(False)
        self.restart_btn.show()

    def reset_board(self):
        self.board = [""] * (self.n * self.n)
        self.turn = "X"
        self.info_label.setText(self.start_text)
        self.restart_btn.hide()
        for b in self.buttons:
            b.setText("")
            b.setEnabled(True)
            b.setStyleSheet(self.cell_style(ACCENT, "#3a2e22"))


class ResultDialog(QDialog):
    """Uzun cevaplar (makale, kod) için okuma / kopyalama / kaydetme penceresi."""
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.text = text
        self.setWindowTitle(f"KATIA - {title}")
        self.resize(820, 620)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")
        lay = QVBoxLayout(self)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setPlainText(text)
        self.view.setFont(QFont("Consolas", 11))
        self.view.setStyleSheet(f"background:#0a0806; border:1px solid {LINE2}; padding:10px;")
        lay.addWidget(self.view)
        row = QHBoxLayout()
        b1, b2, b3 = flat_btn("KOPYALA"), flat_btn("KAYDET"), flat_btn("KAPAT")
        b1.clicked.connect(lambda: QApplication.clipboard().setText(self.text))
        b2.clicked.connect(self.save)
        b3.clicked.connect(self.close)
        row.addStretch()
        for b in (b1, b2, b3):
            row.addWidget(b)
        lay.addLayout(row)

    def save(self):
        ext = ".py" if "```python" in self.text else (".html" if "```html" in self.text else ".txt")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "katia_cikti" + ext)
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", desktop)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text)


class SettingsDialog(QDialog):
    THEMES = {
        "Altın (varsayılan)": {"ACCENT": "#c9a27a", "PINK": "#ff3b6b"},
        "Mavi": {"ACCENT": "#5aa9ff", "PINK": "#ff5a8a"},
        "Yeşil": {"ACCENT": "#4cff9a", "PINK": "#ff6b6b"},
        "Kırmızı": {"ACCENT": "#ff4d4d", "PINK": "#ffb347"},
        "Mor": {"ACCENT": "#b57bff", "PINK": "#ff7bd5"},
    }
    BGS = {"Siyah": "#050403", "Koyu gri": "#101216", "Lacivert": "#060a14"}

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("KATIA - AYARLAR")
        self.setFixedSize(620, 560)
        self.setStyleSheet(
            f"QDialog{{background:{BG};}} QLabel, QCheckBox{{color:{TEXT};}} "
            f"QTabWidget::pane{{border:1px solid {LINE2};}} "
            f"QTabBar::tab{{background:{BG}; color:{DIM}; padding:8px 12px; border:1px solid {LINE2};}} "
            f"QTabBar::tab:selected{{color:{ACCENT};}} "
            f"QComboBox, QSpinBox, QLineEdit, QTextEdit{{background:#0a0806; color:{TEXT}; "
            f"border:1px solid {LINE2}; padding:6px;}}")
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        def tab(title):
            w = QWidget()
            l = QVBoxLayout(w)
            tabs.addTab(w, title)
            return l

        # --- GENEL
        g = tab("GENEL")
        g.addWidget(mk_label("GROQ API ANAHTARI", 9, 3, ACCENT))
        self.key = QLineEdit(cfg.get("groq_api_key", ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("gsk_...")
        g.addWidget(self.key)
        g.addWidget(mk_label("WHATSAPP KİŞİLERİ (her satır: isim=numara)", 9, 2, ACCENT))
        self.contacts = QTextEdit()
        self.contacts.setPlainText("\n".join(f"{k}={v}" for k, v in cfg.get("contacts", {}).items()))
        g.addWidget(self.contacts)

        # --- GÖRÜNÜM
        v = tab("GÖRÜNÜM")
        th = cfg.get("theme", {})
        v.addWidget(mk_label("RENK TEMASI", 9, 3, ACCENT))
        self.theme = QComboBox()
        self.theme.addItems(list(self.THEMES))
        self.theme.setCurrentText(th.get("name", "Altın (varsayılan)"))
        v.addWidget(self.theme)
        v.addWidget(mk_label("ARKA PLAN", 9, 3, ACCENT))
        self.bg = QComboBox()
        self.bg.addItems(list(self.BGS))
        self.bg.setCurrentText(th.get("bgname", "Siyah"))
        v.addWidget(self.bg)
        v.addWidget(mk_label("Görünüm değişiklikleri Katia yeniden açılınca uygulanır.", 8, 1))
        v.addStretch()

        # --- SES
        s = tab("SES")
        vc = cfg.get("voice", {})
        self.voice_on = QCheckBox("Katia sesli konuşsun")
        self.voice_on.setChecked(vc.get("on", True))
        s.addWidget(self.voice_on)
        s.addWidget(mk_label("KONUŞMA HIZI (80-300)", 9, 3, ACCENT))
        self.rate = QSpinBox()
        self.rate.setRange(80, 300)
        self.rate.setValue(int(vc.get("rate", 165)))
        s.addWidget(self.rate)
        s.addWidget(mk_label("SES SEVİYESİ (0-100)", 9, 3, ACCENT))
        self.vol = QSpinBox()
        self.vol.setRange(0, 100)
        self.vol.setValue(int(vc.get("volume", 100)))
        s.addWidget(self.vol)
        s.addStretch()

        # --- LED
        led = cfg.get("led", {})
        l = tab("LED / ODA")
        l.addWidget(mk_label("BAĞLANTI TÜRÜ", 9, 3, ACCENT))
        self.led_mode = QComboBox()
        self.led_mode.addItems(["yok", "broadlink", "http"])
        self.led_mode.setCurrentText(led.get("mode", "yok"))
        l.addWidget(self.led_mode)
        l.addWidget(mk_label("BROADLINK IR CİHAZ IP ADRESİ", 9, 3, ACCENT))
        hrow = QHBoxLayout()
        self.led_host = QLineEdit(led.get("host", ""))
        self.led_host.setPlaceholderText("192.168.1.50")
        find = flat_btn("CİHAZ BUL", ACCENT, 8)
        find.clicked.connect(self.find_devices)
        hrow.addWidget(self.led_host)
        hrow.addWidget(find)
        l.addLayout(hrow)
        l.addWidget(mk_label("HTTP MODU: her satır komut=adres  (ESP32 / WLED / Tasmota)", 9, 2, ACCENT))
        self.led_urls = QTextEdit()
        self.led_urls.setPlainText("\n".join(f"{k}={u}" for k, u in led.get("urls", {}).items()))
        self.led_urls.setPlaceholderText("ac=http://192.168.1.60/on\nkapat=http://192.168.1.60/off")
        l.addWidget(self.led_urls)
        self.led_info = mk_label("Broadlink: 'led öğren ac' de, sonra kumandadan tuşa bas.", 8, 1)
        self.led_info.setWordWrap(True)
        l.addWidget(self.led_info)

        # --- TELEFON / WEB
        web = cfg.get("web", {})
        w = tab("TELEFON / WEB")
        self.web_on = QCheckBox("Telefon / web arayüzünü aç")
        self.web_on.setChecked(web.get("on", False))
        w.addWidget(self.web_on)
        w.addWidget(mk_label("PORT", 9, 3, ACCENT))
        self.web_port = QSpinBox()
        self.web_port.setRange(1024, 65535)
        self.web_port.setValue(int(web.get("port", 8765)))
        w.addWidget(self.web_port)
        w.addWidget(mk_label("SAHİP KODU (tam yetki - boşsa otomatik üretilir)", 9, 2, ACCENT))
        self.web_owner = QLineEdit(web.get("owner", ""))
        w.addWidget(self.web_owner)
        w.addWidget(mk_label("MİSAFİR KODU (sadece sohbet, PC'yi kontrol edemez)", 9, 2, ACCENT))
        self.web_guest = QLineEdit(web.get("guest", ""))
        w.addWidget(self.web_guest)
        info = mk_label(f"Adres: http://{local_ip()}:{self.web_port.value()}", 9, 2, TEXT)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        w.addWidget(info)
        w.addStretch()

        row = QHBoxLayout()
        save, close = flat_btn("KAYDET", ACCENT), flat_btn("İPTAL")
        save.clicked.connect(self.save)
        close.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(save)
        row.addWidget(close)
        lay.addLayout(row)

    def find_devices(self):
        self.led_info.setText("Aranıyor (5 sn)...")
        QApplication.processEvents()
        found = LedController.discover()
        if found:
            self.led_host.setText(found[0])
            self.led_info.setText("Bulundu: " + ", ".join(found))
        else:
            self.led_info.setText("Cihaz bulunamadı. IP'yi elle girebilirsin (pip install broadlink gerekli).")

    def save(self):
        import secrets
        self.cfg["groq_api_key"] = self.key.text().strip()
        contacts = {}
        for line in self.contacts.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                contacts[tr_lower(k.strip())] = v.strip()
        self.cfg["contacts"] = contacts

        th = dict(self.THEMES[self.theme.currentText()])
        th["BG"] = self.BGS[self.bg.currentText()]
        th["name"], th["bgname"] = self.theme.currentText(), self.bg.currentText()
        self.cfg["theme"] = th

        self.cfg["voice"] = {"on": self.voice_on.isChecked(), "rate": self.rate.value(), "volume": self.vol.value()}

        urls = {}
        for line in self.led_urls.toPlainText().splitlines():
            if "=" in line:
                k, u = line.split("=", 1)
                urls[k.strip()] = u.strip()
        old_codes = self.cfg.get("led", {}).get("codes", {})
        self.cfg["led"] = {"mode": self.led_mode.currentText(), "host": self.led_host.text().strip(),
                           "urls": urls, "codes": old_codes}

        owner = self.web_owner.text().strip()
        if self.web_on.isChecked() and not owner:
            owner = secrets.token_hex(4)
        self.cfg["web"] = {"on": self.web_on.isChecked(), "port": self.web_port.value(),
                           "owner": owner, "guest": self.web_guest.text().strip()}
        save_config(self.cfg)
        self.accept()


# =====================================================================
#                              ANA PENCERE
# =====================================================================
class KatiaWindow(QMainWindow):
    web_request = pyqtSignal(str, str, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("KATIA")
        self.resize(1400, 820)
        self.setStyleSheet(f"QMainWindow, QWidget#root {{background:{BG};}} "
                           f"QToolTip {{color:#000; background:{ACCENT};}}")

        self.cfg = load_config()
        self.user_memory = load_hafiza()
        self.groq_client = None
        self.init_groq()

        self.history, self.workers, self.dialogs = [], set(), []
        self._web_fut = None
        self.attached = None
        self.listening = False
        self.weather = None
        self.mode = None            # None / "timer" / "sw"
        self.timer_end = self.timer_total = 0
        self.sw_running, self.sw_start, self.sw_elapsed, self.sw_step = False, 0, 0, 0
        self.reminders = []

        self.speaker = Speaker(self.cfg)
        self.speaker.speaking.connect(self.on_speaking)
        self.speaker.start()

        self.led = LedController(self.cfg, save_config)
        self.web = None
        self.web_request.connect(self.on_web_request)

        if winsound:
            try:
                winsound.Beep(1000, 150)
            except Exception:
                pass

        self.build_ui()

        QShortcut(QKeySequence("F4"), self, activated=self.toggle_mic)

        self.slow = QTimer(self)
        self.slow.timeout.connect(self.update_live_data)
        self.slow.start(1000)
        self.fast = QTimer(self)
        self.fast.timeout.connect(self.tick_fast)
        self.fast.start(200)
        self.wtimer = QTimer(self)
        self.wtimer.timeout.connect(self.refresh_weather)
        self.wtimer.start(15 * 60 * 1000)

        self.update_live_data()
        self.refresh_weather()
        self.start_web()
        self.say("Buradayım patron, sistemler devrede, ne yapıyoruz?")

    # ------------------------------------------------------------ UI
    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 22, 28, 18)

        # ---- ÜST ÇUBUK
        head = QHBoxLayout()
        head.addWidget(mk_label("K A T I A", 15, 6, TEXT, True))
        head.addSpacing(18)
        self.state_lbl = mk_label("SESSİZ", 9, 4)
        head.addWidget(self.state_lbl)
        head.addStretch()
        self.mic_btn = flat_btn("● MİKROFON KAPALI", PINK, 9, False, True)
        self.mic_btn.clicked.connect(self.toggle_mic)
        head.addWidget(self.mic_btn)
        head.addWidget(mk_label("●  KAMERA KAPALI", 9, 3))
        ai_btn = flat_btn("AI MODELLERİ", DIM, 9, False)
        ai_btn.clicked.connect(self.open_ai_models_dialog)
        head.addWidget(ai_btn)
        set_btn = flat_btn("AYARLAR", DIM, 9, False)
        set_btn.clicked.connect(self.open_settings)
        head.addWidget(set_btn)
        self.head_clock = mk_label("--:--", 10, 4, TEXT, True)
        head.addWidget(self.head_clock)
        outer.addLayout(head)
        outer.addSpacing(14)

        body = QHBoxLayout()
        body.setSpacing(28)
        outer.addLayout(body, 1)

        # ---- SOL PANEL
        left = QVBoxLayout()
        left.setSpacing(10)
        self.clock_ring = RingWidget(130, 4, ACCENT, 20)
        left.addWidget(self.clock_ring, alignment=Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(mk_label("ZAMAN", 9, 4))
        self.date_lbl = mk_label("", 9, 3, TEXT)
        left.addWidget(self.date_lbl)
        left.addWidget(sep())

        sysrow = QHBoxLayout()
        self.cpu_ring = RingWidget(90, 4, ACCENT, 17, 7)
        sysrow.addWidget(self.cpu_ring)
        sysinfo = QVBoxLayout()
        sysinfo.addWidget(mk_label("SİSTEM", 9, 4))
        self.pil_lbl, self.ram_lbl, self.disk_lbl = (mk_label("", 9, 2, TEXT) for _ in range(3))
        for lb in (self.pil_lbl, self.ram_lbl, self.disk_lbl):
            sysinfo.addWidget(lb)
        sysrow.addLayout(sysinfo)
        left.addLayout(sysrow)
        left.addWidget(sep())

        self.timer_ring = RingWidget(170, 3, ACCENT, 22)
        self.timer_ring.set(0, "--:--", "HAZIR")
        left.addWidget(self.timer_ring, alignment=Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(mk_label("ZAMANLAYICI", 9, 4))
        tl = mk_label("“ON DAKİKALIK ZAMANLAYICI KUR” DE", 8, 2)
        tl.setWordWrap(True)
        left.addWidget(tl)
        prow = QHBoxLayout()
        for txt, mins in (("1 DK", 1), ("5 DK", 5), ("10 DK", 10), ("25 DK", 25)):
            b = flat_btn(txt, DIM, 8)
            b.clicked.connect(lambda _, m=mins: self.start_timer(m * 60))
            prow.addWidget(b)
        left.addLayout(prow)
        self.sw_btn = flat_btn("⏱  KRONOMETRE", DIM, 8)
        self.sw_btn.clicked.connect(self.toggle_stopwatch)
        left.addWidget(self.sw_btn)
        left.addStretch()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(320)
        body.addWidget(lw)

        # ---- ORTA PANEL
        center = QVBoxLayout()
        self.orb = OrbWidget()
        self.orb.clicked.connect(self.toggle_mic)
        center.addWidget(self.orb, 1)
        self.hint_lbl = mk_label("", 9, 3)
        self.hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_lbl.setWordWrap(True)
        center.addWidget(self.hint_lbl)
        self.reply = QTextBrowser()
        self.reply.setFixedHeight(120)
        self.reply.setStyleSheet("background:transparent; border:none; font-size:16px; color:#ffffff;")
        center.addWidget(self.reply)

        inrow = QHBoxLayout()
        att = flat_btn("📎", TEXT, 12, False)
        att.clicked.connect(self.attach_file)
        inrow.addWidget(att)
        inrow.addWidget(mk_label("›", 12, 0, ACCENT))
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("KONUŞ YA DA YAZ")
        self.input_box.setFont(QFont("Consolas", 11))
        self.input_box.setStyleSheet(f"background:transparent; border:none; color:{TEXT}; padding:10px;")
        self.input_box.returnPressed.connect(self.handle_input)
        inrow.addWidget(self.input_box)
        send = flat_btn("YAZ ↵", DIM, 9, False)
        send.clicked.connect(self.handle_input)
        inrow.addWidget(send)
        frame = QFrame()
        frame.setStyleSheet(f"border-top:1px solid {LINE};")
        frame.setLayout(inrow)
        center.addWidget(frame)
        body.addLayout(center, 1)

        # ---- SAĞ PANEL
        right = QVBoxLayout()
        right.setSpacing(8)
        wc = QFrame()
        wc.setStyleSheet(f"QFrame{{border:1px solid {LINE2}; background:#0a0806;}} QLabel{{border:none;}}")
        wl = QGridLayout(wc)
        self.w_temp = mk_label("--°", 26, 2, TEXT, True)
        self.w_city = mk_label("", 9, 3, TEXT)
        self.w_cond = mk_label("", 9, 2, DIM)
        self.w_icon = mk_label("", 16, 0, DIM)
        self.w_lo, self.w_hi = mk_label("", 8, 1), mk_label("", 8, 1)
        self.w_bar = RangeBar()
        wl.addWidget(self.w_temp, 0, 0, 2, 1)
        wl.addWidget(self.w_city, 0, 1)
        wl.addWidget(self.w_cond, 1, 1)
        wl.addWidget(self.w_icon, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        barrow = QHBoxLayout()
        barrow.addWidget(self.w_lo)
        barrow.addWidget(self.w_bar, 1)
        barrow.addWidget(self.w_hi)
        wl.addLayout(barrow, 2, 0, 1, 3)
        right.addWidget(wc)
        right.addWidget(mk_label("HAVA", 9, 4))

        right.addWidget(mk_label("TAKVİM", 9, 4))
        right.addWidget(mk_label("0  BUGÜN", 16, 2, TEXT, True))
        right.addWidget(mk_label("Bugün takviminde etkinlik yok.", 9, 1))
        right.addWidget(mk_label("ANIMSATICILAR", 9, 4))
        self.rem_count = mk_label("0  AÇIK", 16, 2, TEXT, True)
        right.addWidget(self.rem_count)
        self.rem_text = mk_label("Bekleyen anımsatıcı yok.", 9, 1)
        self.rem_text.setWordWrap(True)
        right.addWidget(self.rem_text)

        self.map = MapWidget()
        right.addWidget(self.map)
        right.addWidget(mk_label("HARİTA", 9, 4))
        self.map_lbl = mk_label("", 9, 3, TEXT)
        right.addWidget(self.map_lbl)
        right.addWidget(mk_label("© OpenStreetMap katkıcıları", 8, 1))
        right.addStretch()
        brow = QHBoxLayout()
        brow.addStretch()
        info = flat_btn("ⓘ", DIM, 11)
        info.clicked.connect(self.show_help)
        close = flat_btn("⏻  KAPAT", DIM, 9)
        close.clicked.connect(self.close)
        brow.addWidget(info)
        brow.addWidget(close)
        right.addLayout(brow)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(380)
        body.addWidget(rw)

        self.set_state("idle")
        self.set_hint(self.default_hint())

    # ------------------------------------------------------- durum / konuşma
    def default_hint(self):
        if SR_AVAILABLE:
            return "Mikrofon kapalı: seni duymam için MİKROFON düğmesine ya da F4'e bas."
        return "Sesli giriş için: pip install SpeechRecognition pyaudio  (şimdilik yazabilirsin)"

    def set_hint(self, t):
        self.hint_lbl.setText(t)

    def set_state(self, s):
        self.orb.set_state(s)
        names = {"idle": "SESSİZ", "listen": "DİNLİYOR", "think": "DÜŞÜNÜYOR", "speak": "KONUŞUYOR"}
        self.state_lbl.setText(names[s])

    def on_speaking(self, b):
        if b:
            self.set_state("speak")
        elif not self.listening:
            self.set_state("idle")

    def say(self, text, speak_text=None):
        """Cevabı ekranda göster ve sesli oku."""
        muted = False
        fut = self._web_fut
        if fut is not None and not fut.done():
            fut.set_result(text)
            self._web_fut = None
            muted = True
        body = html.escape(text).replace("\n", "<br>")
        self.reply.setHtml(f"<div align='center' style='color:#fff;font-size:16px;'>{body}</div>")
        t = speak_text if speak_text is not None else text
        t = re.sub(r"```.*?```", " kod bloğu ", t, flags=re.S)
        t = re.sub(r"[*#`_>|]", "", re.sub(r"<[^>]+>", "", t)).strip()
        if len(t) > 350:
            t = t[:350].rsplit(" ", 1)[0] + "."
        if t and not muted:
            self.speaker.say(t)

    def run_async(self, fn, cb, *args):
        w = Worker(fn, *args)
        w.done.connect(cb)
        w.finished.connect(lambda: self.workers.discard(w))
        self.workers.add(w)
        w.start()

    # ---------------------------------------------------------- groq
    def get_api_key(self):
        for k in (self.cfg.get("groq_api_key", ""), os.environ.get("GROQ_API_KEY", ""), GROQ_API_KEY):
            if k and k != PLACEHOLDER:
                return k
        return None

    def init_groq(self):
        self.groq_client = None
        key = self.get_api_key()
        if GROQ_AVAILABLE and key:
            try:
                self.groq_client = Groq(api_key=key)
            except Exception as e:
                print(f"Groq Bağlantı Hatası: {e}")

    def query_groq_ai(self, prompt, hist, long_mode=False):
        if not self.groq_client:
            return "Groq API anahtarı yok patron. AYARLAR'dan gir ya da GROQ_API_KEY tanımla."
        now = datetime.now()
        system = (
            "Sen Katia'sın: zeki, samimi, hızlı ve işini bilen bir Türk asistansın. "
            "Kullanıcıya 'patron' diye hitap et. Türkçe konuş; sıradan sorularda kısa ve net ol. "
            "Kod istenirse eksiksiz, çalışır kodu markdown kod bloğunda ver. "
            "Makale/yazı istenirse tam, düzenli ve akıcı yaz. "
            "Mesajda [İNTERNET ARAMA SONUÇLARI] varsa onlara dayan ve kaynakları an. "
            f"Şu an: {now.strftime('%d.%m.%Y %H:%M')}."
        )
        models = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        last_error = ""
        for m in models:
            try:
                r = self.groq_client.chat.completions.create(
                    messages=[{"role": "system", "content": system}] + hist + [{"role": "user", "content": prompt}],
                    model=m, max_tokens=4096 if long_mode else 700)
                return r.choices[0].message.content
            except Exception as e:
                last_error = str(e)
        return f"Groq Hatası (Detay): {last_error}"

    def ai_job(self, prompt, hist, long_mode, use_web):
        if use_web:
            prompt = f"{prompt}\n\n[İNTERNET ARAMA SONUÇLARI]\n{web_search(prompt)}"
        return self.query_groq_ai(prompt, hist, long_mode)

    def ask_ai(self, text, force_web=False, extra="", guest=False):
        low = tr_lower(text)
        long_mode = any(k in low for k in (
            "makale", "kod", "script", "program", "rapor", "kompozisyon", "dilekçe", "html", "css",
            "javascript", "python", "fonksiyon", "essay", "mektup", "proje"))
        use_web = force_web or any(k in low for k in (
            "güncel", "haber", "son dakika", "internette", "dolar", "euro", "altın", "skor",
            "maç sonucu", "bitcoin", "borsa", "bugün ne oldu"))
        prompt = text
        if self.attached and not guest:
            name, content = self.attached
            prompt = f"{text}\n\n[EKLİ DOSYA: {name}]\n{content}"
            self.attached = None
        if extra:
            prompt = f"{text}\n\n{extra}"
        self.set_state("think")
        self.set_hint("Düşünüyorum..." + (" (internette arıyorum)" if use_web else ""))
        hist = [] if guest else list(self.history[-10:])
        self.run_async(self.ai_job, lambda r, t=text, g=guest: self.ai_done(r, t, g), prompt, hist, long_mode, use_web)

    def ai_done(self, result, user_text, guest=False):
        self.set_hint(self.default_hint())
        self.set_state("idle")
        if isinstance(result, Exception):
            return self.say(f"Bir hata oldu patron: {result}")
        if not guest:
            self.history += [{"role": "user", "content": user_text}, {"role": "assistant", "content": result}]
            self.history = self.history[-20:]
        web_pending = self._web_fut is not None and not self._web_fut.done()
        if (len(result) > 400 or "```" in result) and not web_pending:
            dlg = ResultDialog(self, "CEVAP", result)
            dlg.show()
            self.dialogs.append(dlg)
            self.say("Cevap uzun olduğu için ayrı pencerede açtım patron. Kopyalayabilir veya kaydedebilirsin.")
        else:
            self.say(result)

    # ----------------------------------------------------------- mikrofon
    def toggle_mic(self):
        if self.listening:
            return
        if not SR_AVAILABLE:
            return self.set_hint("SpeechRecognition ve pyaudio kurulu değil: pip install SpeechRecognition pyaudio")
        self.listening = True
        self.mic_btn.setText("● MİKROFON AÇIK")
        self.mic_btn.setStyleSheet(self.mic_btn.styleSheet().replace(PINK, "#4cff9a"))
        self.set_state("listen")
        self.set_hint("Dinliyorum patron, konuş...")
        self.run_async(self.listen_job, self.heard)

    @staticmethod
    def listen_job():
        r = sr.Recognizer()
        with sr.Microphone() as src:
            r.adjust_for_ambient_noise(src, 0.5)
            audio = r.listen(src, timeout=6, phrase_time_limit=12)
        return r.recognize_google(audio, language="tr-TR")

    def heard(self, result):
        self.listening = False
        self.mic_btn.setText("● MİKROFON KAPALI")
        self.mic_btn.setStyleSheet(self.mic_btn.styleSheet().replace("#4cff9a", PINK))
        self.set_state("idle")
        self.set_hint(self.default_hint())
        if isinstance(result, Exception):
            return self.say("Seni duyamadım patron, tekrar dener misin?")
        self.input_box.setText(result)
        self.handle_input()

    # -------------------------------------------------- canlı veri / sayaçlar
    def update_live_data(self):
        now = datetime.now()
        self.clock_ring.set((now.hour * 60 + now.minute) / 1440, now.strftime("%H:%M"), value2=now.second / 60)
        self.head_clock.setText(now.strftime("%H:%M"))
        self.date_lbl.setText(f"{GUNLER[now.weekday()]} · {now.day} {AYLAR[now.month - 1]}")
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep)).percent
        except Exception:
            disk = 0
        self.cpu_ring.set(cpu / 100, str(int(cpu)), "CPU %")
        self.pil_lbl.setText(f"PİL   {self.battery_text()}")
        self.ram_lbl.setText(f"RAM   %{int(ram)}")
        self.disk_lbl.setText(f"DİSK  %{int(disk)} dolu")

    @staticmethod
    def battery_text():
        try:
            b = psutil.sensors_battery()
            if b is None:
                return "yok (masaüstü)"
            return f"%{int(b.percent)} · {'şarj' if b.power_plugged else 'pilde'}"
        except Exception:
            return "?"

    def system_report(self):
        return (f"Pil {self.battery_text()}. RAM yüzde {int(psutil.virtual_memory().percent)}, "
                f"işlemci yüzde {int(psutil.cpu_percent(0.3))}, "
                f"disk yüzde {int(psutil.disk_usage(os.path.abspath(os.sep)).percent)} dolu.")

    def start_timer(self, seconds):
        self.sw_running = False
        self.mode = "timer"
        self.timer_total = seconds
        self.timer_end = time.time() + seconds
        self.sw_btn.setText("⏱  KRONOMETRE")
        self.sw_step = 0
        m = seconds // 60
        self.say(f"{m} dakikalık zamanlayıcı kuruldu patron." if seconds >= 60 else f"{seconds} saniyelik zamanlayıcı kuruldu.")

    def cancel_timer(self):
        if self.mode == "timer":
            self.mode = None
            self.timer_ring.set(0, "--:--", "HAZIR")
            self.say("Zamanlayıcıyı iptal ettim.")
        else:
            self.say("Çalışan bir zamanlayıcı yok patron.")

    def toggle_stopwatch(self):
        if self.mode == "timer":
            self.mode = None
        if self.sw_step == 0:
            self.mode, self.sw_running, self.sw_start, self.sw_elapsed = "sw", True, time.time(), 0
            self.sw_step = 1
            self.sw_btn.setText("⏱  DURDUR")
        elif self.sw_step == 1:
            self.sw_running = False
            self.sw_elapsed = time.time() - self.sw_start
            self.sw_step = 2
            self.sw_btn.setText("⏱  SIFIRLA")
        else:
            self.sw_step, self.mode = 0, None
            self.sw_btn.setText("⏱  KRONOMETRE")
            self.timer_ring.set(0, "--:--", "HAZIR")

    def tick_fast(self):
        if self.mode == "timer":
            remain = self.timer_end - time.time()
            if remain <= 0:
                self.mode = None
                self.timer_ring.set(0, "00:00", "BİTTİ")
                if winsound:
                    try:
                        winsound.Beep(1200, 400)
                        winsound.Beep(1500, 400)
                    except Exception:
                        pass
                self.say("Zamanlayıcı bitti patron!")
                QTimer.singleShot(4000, lambda: self.mode is None and self.timer_ring.set(0, "--:--", "HAZIR"))
            else:
                r = int(math.ceil(remain))
                self.timer_ring.set(remain / self.timer_total, f"{r // 60:02d}:{r % 60:02d}", "KALDI")
        elif self.mode == "sw":
            el = (time.time() - self.sw_start) if self.sw_running else self.sw_elapsed
            self.timer_ring.set((el % 60) / 60, f"{int(el) // 60:02d}:{int(el) % 60:02d}", "KRONOMETRE")
        now = time.time()
        due = [r for r in self.reminders if r[0] <= now]
        if due:
            self.reminders = [r for r in self.reminders if r[0] > now]
            for _, txt in due:
                if winsound:
                    try:
                        winsound.Beep(1000, 300)
                    except Exception:
                        pass
                self.say(f"Hatırlatma patron: {txt}")
            self.refresh_reminders()

    def add_reminder(self, seconds, text):
        self.reminders.append((time.time() + seconds, text))
        self.refresh_reminders()
        self.say(f"Tamamdır patron, hatırlatacağım: {text}")

    def refresh_reminders(self):
        self.rem_count.setText(f"{len(self.reminders)}  AÇIK")
        if self.reminders:
            nxt = sorted(self.reminders)[0]
            self.rem_text.setText(f"Sıradaki: {nxt[1]} ({datetime.fromtimestamp(nxt[0]).strftime('%H:%M')})")
        else:
            self.rem_text.setText("Bekleyen anımsatıcı yok.")

    # ------------------------------------------------------------ hava
    def refresh_weather(self):
        self.run_async(fetch_location_weather, self.weather_done)

    def weather_done(self, d):
        if isinstance(d, Exception):
            return
        self.weather = d
        self.w_temp.setText(f"{round(d['temp'])}°")
        self.w_city.setText(tr_upper(d["city"]))
        self.w_cond.setText(d["cond"])
        self.w_icon.setText(d["icon"])
        self.w_lo.setText(f"{round(d['tmin'])}°")
        self.w_hi.setText(f"{round(d['tmax'])}°")
        self.w_bar.set(d["tmin"], d["tmax"], d["temp"])
        self.map.set_data(d.get("tile"), f"{d['lat']:.3f}°  {d['lon']:.3f}°")
        self.map_lbl.setText(f"{tr_upper(d['city'])}  ·  {tr_upper(d['country'])}")

    def weather_voice(self):
        d = self.weather
        if not d:
            return "Hava verisini henüz alamadım patron."
        return (f"{d['city']}'da hava {d['cond']}, {round(d['temp'])} derece. "
                f"En düşük {round(d['tmin'])}, en yüksek {round(d['tmax'])}.")

    # ------------------------------------------------------- diyaloglar
    def open_ai_models_dialog(self):
        self.ai_dlg = AIModelsDialog(self)
        self.ai_dlg.exec()

    def open_settings(self):
        if SettingsDialog(self, self.cfg).exec():
            self.init_groq()
            self.led.reload(self.cfg)
            self.start_web()
            self.say("Ayarlar kaydedildi patron. Renk değişikliği için beni yeniden aç." +
                     ("" if self.groq_client else " Ama Groq anahtarı hâlâ eksik."))

    def attach_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Dosya ekle")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.attached = (os.path.basename(path), f.read(12000))
            self.set_hint(f"Ekli dosya: {os.path.basename(path)} — şimdi ne yapmamı istediğini yaz.")
        except Exception as e:
            self.set_hint(f"Dosya okunamadı: {e}")

    def show_help(self):
        QMessageBox.information(self, "KATIA - Komutlar", (
            "• saat kaç / bugün günlerden ne\n"
            "• pil durumu / sistem durumu / ram\n"
            "• hava durumu / ankara hava durumu\n"
            "• 10 dakika zamanlayıcı kur / zamanlayıcıyı iptal et\n"
            "• 15 dakika sonra su içmemi hatırlat\n"
            "• kronometre\n"
            "• whatsapp ahmet: toplantı 5'te   |   ali'ye whatsapp'tan geliyorum yaz\n"
            "• youtube aç / github aç / siteadi.com aç\n"
            "• youtube'da lofi izle / amazon'da kulaklık ara / google kedi\n"
            "• ara <konu>  (internette arar ve özetler)\n"
            "• oku <site adresi>  (sayfayı okuyup özetler)\n"
            "• görsel <konu>\n"
            "• python ile hesap makinesi kodu yaz / yapay zeka hakkında makale yaz\n"
            "• xox / xoox\n"
            "• 📎 ile dosya ekleyip hakkında soru sor\n"
            "• ışığı aç / ışığı kapat / led kırmızı / parlaklığı artır\n"
            "• led öğren kırmızı  (IR kumanda tuşunu öğretir)"))

    # ------------------------------------------------------ komut yönlendirme
    def handle_input(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self.set_hint(f"› {text}")
        self.route(text)

    def open_url(self, url, msg):
        webbrowser.open(url)
        self.say(msg)

    def send_whatsapp(self, who, msg):
        who_l = tr_lower(who.strip())
        num = normalize_phone(who) or normalize_phone(self.cfg.get("contacts", {}).get(who_l, ""))
        if not num:
            return self.say(f"'{who}' için numara bulamadım patron. AYARLAR'dan 'isim=numara' diye ekleyebilirsin.")
        web_url = f"https://wa.me/{num}?text={quote(msg)}"
        if WHATSAPP_USE_WEB or not hasattr(os, "startfile"):
            webbrowser.open(web_url)
        else:
            try:
                os.startfile(f"whatsapp://send?phone={num}&text={quote(msg)}")
            except Exception:
                webbrowser.open(web_url)
        if WHATSAPP_AUTO_SEND and PYAUTOGUI_AVAILABLE:
            QTimer.singleShot(9000, lambda: pyautogui.press("enter"))
            self.say(f"{who} kişisine mesajı hazırladım, birazdan gönderiyorum patron.")
        else:
            self.say(f"{who} kişisi için mesaj hazır patron, WhatsApp'ta gönder'e basman yeterli.")

    def route(self, text):
        low = tr_lower(text).strip()
        now = datetime.now()

        # --- oyunlar
        if low == "xox":
            self.say("3x3 XOX tahtası açılıyor, hadi oynayalım patron.")
            return XOXDialog(self, 3, 3).exec()
        if low == "xoox":
            self.say("Devasa 6x6 arena hazır. 4 yapan kazanır, hazır ol patron!")
            return XOXDialog(self, 6, 4).exec()

        # --- saat / tarih
        if re.search(r"saat kaç|saati söyle", low):
            return self.say(f"Saat {now.strftime('%H:%M')} patron.")
        if re.search(r"bugün günlerden|hangi gün|bugünün tarihi|tarih ne", low):
            return self.say(f"Bugün {now.day} {AYLAR[now.month - 1].capitalize()} {now.year}, {GUNLER[now.weekday()].capitalize()}.")

        # --- sistem
        if re.search(r"\b(pil|şarj|batarya)\b", low) and "sistem" not in low:
            return self.say(f"Pil durumu: {self.battery_text()}.")
        if re.search(r"\bram\b|sistem durumu|\bcpu\b|işlemci|kullanılan bellek|\bdisk\b", low):
            return self.say(self.system_report())

        # --- hava
        if re.search(r"hava durumu|hava nasıl|kaç derece|hava kaç", low):
            city = re.sub(r"hava durumu|hava nasıl|kaç derece|hava kaç|nasıl|\bbugün\b|\bşu an\b|['’]", " ", low)
            city = re.sub(r"\b(da|de|ta|te|ın|in)\b", " ", city).strip()
            if city:
                self.set_hint("Hava durumu alınıyor...")
                return self.run_async(city_weather_text, lambda r: self.say(
                    f"Hava bilgisini alamadım: {r}" if isinstance(r, Exception) else r), city)
            return self.say(self.weather_voice())

        # --- zamanlayıcı / hatırlatıcı / kronometre
        tm = re.search(r"(\d+)\s*(saniye|sn|dakika|dk|saat)", low)
        if re.search(r"zamanlayıcı(yı)?\s+(iptal|durdur|kapat|sil)", low):
            return self.cancel_timer()
        if re.search(r"hatırlat|anımsat|animsat", low) and tm:
            secs = int(tm.group(1)) * {"saniye": 1, "sn": 1, "dakika": 60, "dk": 60, "saat": 3600}[tm.group(2)]
            msg = re.sub(r"(\d+)\s*(saniye|sn|dakika|dk|saat)(\s*sonra)?|hatırlat\w*|anımsat\w*|animsat\w*|\bbana\b|\bbeni\b", "", low)
            return self.add_reminder(secs, re.sub(r"\s+", " ", msg).strip() or "zamanın geldi")
        if re.search(r"zamanlayıcı|sayaç|geri sayım", low):
            if tm:
                secs = int(tm.group(1)) * {"saniye": 1, "sn": 1, "dakika": 60, "dk": 60, "saat": 3600}[tm.group(2)]
                return self.start_timer(secs)
            if (w := re.search(r"\b(bir|iki|üç|beş|on|on beş|yirmi|otuz)\b", low)):
                nums = {"bir": 1, "iki": 2, "üç": 3, "beş": 5, "on": 10, "on beş": 15, "yirmi": 20, "otuz": 30}
                return self.start_timer(nums[w.group(1)] * 60)
            return self.say("Kaç dakikalık kurayım patron? Örneğin '5 dakika zamanlayıcı kur' de.")
        if "kronometre" in low:
            self.toggle_stopwatch()
            return self.say("Kronometre " + ("çalışıyor." if self.sw_step == 1 else "durdu." if self.sw_step == 2 else "sıfırlandı."))

        # --- oda ışığı / LED
        if re.search(r"\b(ışık|ışığı|led|ledi|ledleri|lamba|lambayı)\b", low):
            mo = re.search(r"öğren\w*\s+(\S+)", low)
            if mo:
                key = parse_led(mo.group(1)) or mo.group(1)
                if self.led.mode != "broadlink":
                    return self.say("Öğrenme sadece Broadlink modunda çalışır patron. AYARLAR > LED bölümüne bak.")
                self.say(f"'{key}' tuşu için bekliyorum patron. 15 saniye içinde kumandadan o tuşa bas.")
                return self.run_async(self.led.learn, lambda r: self.say(r if isinstance(r, str) else f"Hata: {r}"), key)
            key = parse_led(low)
            if not key:
                return self.say("Işıkla ne yapayım patron? Aç, kapat, kırmızı, mavi, parlaklığı artır gibi söyle.")
            self.set_hint("Işık komutu gönderiliyor...")
            return self.run_async(self.led.send, lambda r: self.say(r if isinstance(r, str) else f"Işığa ulaşamadım: {r}"), key)

        # --- whatsapp
        m = re.match(r"^whatsapp(?:'?tan| üzerinden)?\s+(.+?)\s*[:,]\s*(.+)$", low) \
            or re.match(r"^(\S+?)['’]?(?:a|e|ya|ye|na|ne)\s+whatsapp(?:['’]?tan)?\s+(.+?)(?:\s+(?:yaz|at|gönder|de|söyle))?$", low)
        if m:
            return self.send_whatsapp(m.group(1), m.group(2))
        if low.startswith("whatsapp"):
            return self.say("Şöyle söyle patron: 'whatsapp ahmet: toplantı 5'te' ya da 'ali'ye whatsapp'tan geliyorum yaz'.")

        # --- internet: sayfa oku / ara / görsel
        if low.startswith("oku "):
            url = text.split(" ", 1)[1].strip()
            self.set_hint("Sayfa okunuyor...")

            def read_job():
                return fetch_page_text(url)

            def read_done(r):
                if isinstance(r, Exception):
                    return self.say(f"Sayfayı açamadım patron: {r}")
                self.ask_ai("Bu web sayfasının içeriğini Türkçe özetle.", extra=f"[SAYFA İÇERİĞİ: {url}]\n{r}")
            return self.run_async(read_job, read_done)
        if low.startswith("görsel ") or low.startswith("fotoğraf "):
            q = text.split(" ", 1)[1].strip()
            return self.open_url(f"https://www.google.com/search?tbm=isch&q={quote_plus(q)}", f"'{q}' görsellerini tarayıcıda açtım patron.")
        if low.startswith("ara ") or low.startswith("internette ara "):
            q = text.split(" ", 1)[1].strip() if low.startswith("ara ") else text.split(" ", 2)[2].strip()
            return self.ask_ai(f"{q} hakkında kısa ve güncel bilgi ver.", force_web=True)

        # --- site arama:  youtube'da lofi izle
        names = "|".join(sorted(SEARCH_URLS, key=len, reverse=True))
        m = re.match(rf"^({names})['’]?\s*(?:da|de|ta|te)?\s+(.+?)(?:\s+(?:ara|izle|aç|bul|dinle|göster))?$", low)
        if m and m.group(2) not in ("aç", "ara", "git"):
            site, q = m.group(1), m.group(2)
            return self.open_url(SEARCH_URLS[site].format(quote_plus(q)), f"{site.capitalize()} üzerinde '{q}' için arıyorum patron.")

        # --- site açma
        m = re.match(r"^(.+?)\s+(?:aç|git|başlat)$", low) or re.match(r"^(youtube|google|gmail|github)$", low)
        if m:
            name = m.group(1).strip()
            if name in SITES:
                return self.open_url(SITES[name], f"{name.capitalize()} açılıyor patron.")
            if re.match(r"^(?:https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", name):
                return self.open_url(name if name.startswith("http") else "https://" + name, f"{name} açılıyor patron.")
            if name not in ("uygulama", "program"):
                return self.open_url(f"https://www.google.com/search?q={quote_plus(name)}", f"'{name}' için Google'da arama açtım patron.")
        if re.match(r"^(?:https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", low) and " " not in low:
            return self.open_url(low if low.startswith("http") else "https://" + low, f"{low} açılıyor patron.")

        # --- şehir / ada / hafıza (eski özellikler)
        if low in CITIES_DATA:
            info = CITIES_DATA[low]
            return self.say(f"{low.upper()}: {info['detay']} | Gezilecek: {info['gezilecek']}")
        if low in ISLANDS_DATA:
            info = ISLANDS_DATA[low]
            return self.say(f"{low.upper()} ADASI: {info['detay']} | Gezilecek: {info['gezilecek']}")
        if low in self.user_memory:
            return self.say(self.user_memory[low])

        # --- geri kalan her şey: Groq
        self.ask_ai(text)

    # ------------------------------------------------ telefon / web
    def start_web(self):
        if self.web:
            self.web.stop()
            self.web = None
        if not self.cfg.get("web", {}).get("on"):
            return
        self.web = WebServer(self.cfg, self.web_ask)
        ok, msg = self.web.start()
        if not ok:
            self.web = None
        self.set_hint(msg)

    def web_ask(self, text, role):
        """Flask iş parçacığından çağrılır; cevabı ana iş parçacığından bekler."""
        import concurrent.futures
        fut = concurrent.futures.Future()
        self.web_request.emit(text, role, fut)
        try:
            return fut.result(timeout=90)
        except Exception:
            return "Zaman aşımı oldu, tekrar dene."

    def on_web_request(self, text, role, fut):
        if tr_lower(text).strip() in ("xox", "xoox"):
            return fut.set_result("Oyunlar sadece bilgisayarda açılıyor patron.")
        self._web_fut = fut
        QTimer.singleShot(80000, lambda: fut.done() or fut.set_result("Cevap gelmedi, tekrar dene."))
        if role == "guest":
            self.ask_ai(text, guest=True)      # misafir: sadece sohbet
        else:
            self.route(text)

    def closeEvent(self, e):
        if self.web:
            self.web.stop()
        self.speaker.stop()
        e.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KatiaWindow()
    window.show()
    sys.exit(app.exec())
