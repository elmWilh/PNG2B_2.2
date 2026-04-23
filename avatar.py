#!/usr/bin/env python3
# avatar.py
# Р—Р°РїСѓСЃРє: python avatar.py [preset_name]
# Р—Р°РіСЂСѓР¶Р°РµС‚ РїСЂРµСЃРµС‚ РёР· РїР°РїРєРё Prisset/ РёР»Рё Prissets/ Рё Р·Р°РїСѓСЃРєР°РµС‚ Р°РЅРёРјРёСЂРѕРІР°РЅРЅС‹Р№ Р°РІР°С‚Р°СЂ.

import os
import sys
import json
import time
import math
import random
import traceback

# РРјРїРѕСЂС‚РёСЂСѓРµРј pygame Рё numpy/pyaudio; РѕР±С‘СЂС‚РєРё РґР»СЏ РѕС€РёР±РѕРє РїСЂРё РѕС‚СЃСѓС‚СЃС‚РІРёРё Р±РёР±Р»РёРѕС‚РµРє
try:
    import pygame as py
except Exception as e:
    print("РћС€РёР±РєР°: pygame РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ РёР»Рё РЅРµ Р·Р°РіСЂСѓР¶РµРЅ.")
    print("РЈСЃС‚Р°РЅРѕРІРё pygame: pip install pygame")
    raise

try:
    import numpy as np
except Exception as e:
    print("РћС€РёР±РєР°: numpy РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ.")
    print("РЈСЃС‚Р°РЅРѕРІРё numpy: pip install numpy")
    raise

try:
    import pyaudio
except Exception as e:
    pyaudio = None  # Р‘СѓРґРµРј РїСЂРѕРІРµСЂСЏС‚СЊ РїРѕР·Р¶Рµ Рё РєРѕСЂСЂРµРєС‚РЅРѕ РІС‹С…РѕРґРёС‚СЊ

# Р”Р»СЏ СѓРїСЂР°РІР»РµРЅРёСЏ РѕРєРЅРѕРј РЅР° Windows (С‚РѕР»СЊРєРѕ РµСЃР»Рё РїР»Р°С‚С„РѕСЂРјР° windows)
IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes
        import win32api
        import win32gui
        import win32.lib.win32con as win32con
    except Exception:
        # Р•СЃР»Рё win32 РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ вЂ” РѕСЃС‚Р°РІР»СЏРµРј, РЅРѕ Р±РµР· С„СѓРЅРєС†РёРѕРЅР°Р»Р° AlwaysOnTop/Layered
        win32api = win32gui = win32con = None
        ctypes = None
        wintypes = None

if IS_WINDOWS and ctypes:
    BI_RGB = 0
    DIB_RGB_COLORS = 0

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", wintypes.DWORD * 3),
        ]


# -----------------------
# РЈС‚РёР»РёС‚С‹
# -----------------------
def show_console():
    """РџРѕРєР°Р·Р°С‚СЊ РєРѕРЅСЃРѕР»СЊ (Windows)."""
    if IS_WINDOWS and ctypes:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)


def hide_console():
    """РЎРєСЂС‹С‚СЊ РєРѕРЅСЃРѕР»СЊ (Windows)."""
    if IS_WINDOWS and ctypes:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)


def load_json_safe(path):
    """Р—Р°РіСЂСѓР¶Р°РµС‚ JSON, РІРѕР·РІСЂР°С‰Р°РµС‚ dict РёР»Рё РІРѕР·Р±СѓР¶РґР°РµС‚ РїРѕРЅСЏС‚РЅРѕРµ РёСЃРєР»СЋС‡РµРЅРёРµ."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Р¤РѕСЂРјР°С‚ JSON РЅРµРІРµСЂРµРЅ РІ {path}: {e}")


def clamp(v, a, b):
    return max(a, min(b, v))


# -----------------------
# Avatar
# -----------------------
class Avatar:
    SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}

    def __init__(self, preset_name: str, presets_dirs=("Prisset", "Prissets")):
        self.preset_name = preset_name
        self.presets_dirs = presets_dirs

        # РџРѕРёСЃРє РєР°С‚Р°Р»РѕРіР° РїСЂРµСЃРµС‚Р° (РїРѕРґРґРµСЂР¶РёРІР°РµРј РІР°СЂРёР°РЅС‚С‹ Prisset Рё Prissets)
        self.preset_path = None
        for d in self.presets_dirs:
            candidate = os.path.join(d, preset_name)
            if os.path.isdir(candidate):
                self.preset_path = candidate
                break

        if not self.preset_path:
            raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ РїСЂРµСЃРµС‚ '{preset_name}' РІ РїР°РїРєР°С… {presets_dirs}")

        # РћР¶РёРґР°РµРјС‹Рµ РїСѓС‚Рё
        self.config_path = os.path.join(self.preset_path, "Config.json")
        self.sprites_path = os.path.join(self.preset_path, "Sprites")

        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(f"Config.json РЅРµ РЅР°Р№РґРµРЅ РІ {self.preset_path}")
        if not os.path.isdir(self.sprites_path):
            raise FileNotFoundError(f"РџР°РїРєР° Sprites РЅРµ РЅР°Р№РґРµРЅР° РІ {self.preset_path}")

        # Р—Р°РіСЂСѓР¶Р°РµРј РєРѕРЅС„РёРі (РІР°Р»РёРґР°С†РёСЏ РЅРёР¶Рµ)
        self.config = load_json_safe(self.config_path)

        # РџСЂРѕСЃС‚Р°РІРёРј Р·РЅР°С‡РµРЅРёСЏ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Рё СЂР°СЃРїР°СЂСЃРёРј РєРѕРЅС„РёРі
        self._parse_config()

        # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј Pygame (display) РґРѕ Р·Р°РіСЂСѓР·РєРё РёР·РѕР±СЂР°Р¶РµРЅРёР№
        py.init()
        self.hwnd = None
        self.window_pos = None
        self.use_alpha_window = False
        self.layered_dc = None
        self.layered_bitmap = None
        self.layered_bitmap_prev = None
        self.layered_bits_ptr = None

        icon_path = "PNG2B.ico"
        if os.path.exists(icon_path):
            try:
                icon = py.image.load(icon_path)
                py.display.set_icon(icon)
            except Exception as e:
                print("РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёРєРѕРЅРєСѓ:", e)

        # РЎРѕР·РґР°С‘Рј СЌРєСЂР°РЅ Р”Рћ Р·Р°РіСЂСѓР·РєРё СЃРїСЂР°Р№С‚РѕРІ вЂ” СЌС‚Рѕ РЅСѓР¶РЅРѕ РґР»СЏ .convert_alpha()
        self.screen = py.display.set_mode(self.window_size, py.NOFRAME)
        py.display.set_caption(f"PNG2B - {self.preset_name}")

        self._configure_window()

        self._load_sprites()

        # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј Р°СѓРґРёРѕ (РјРёРєСЂРѕС„РѕРЅ)
        self._init_audio()

        # Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅС‹Рµ СЃРѕСЃС‚РѕСЏРЅРёСЏ РґР»СЏ Р°РЅРёРјР°С†РёРё
        self._init_state()
        self.avatar_surface = py.Surface(self.window_size, py.SRCALPHA)

        # РџРѕРєР°Р·С‹РІР°РµРј/РїСЂСЏС‡РµРј РєРѕРЅСЃРѕР»СЊ РІ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё РѕС‚ DebugMode
        if not self.debug:
            hide_console()
        else:
            show_console()

    # -----------------------
    # РџР°СЂСЃРёРЅРі Рё РґРµС„РѕР»С‚С‹
    # -----------------------
    def _parse_config(self):
        c = self.config

        # Window
        win = c.get("Window", {})
        size = win.get("Size", [750])
        if not isinstance(size, (list, tuple)):
            # РґРѕРїСѓСЃС‚РёС‚СЊ РѕРґРёРЅ int, РїСЂРµРІСЂР°С‚РёС‚СЊ РІ СЃРїРёСЃРѕРє
            size = [size]
        if len(size) == 1:
            self.window_size = (int(size[0]), int(size[0]))
        else:
            self.window_size = (int(size[0]), int(size[1]))

        self.scale = float(win.get("Scale", 1.0))
        self.reflect = bool(win.get("Reflect", False))
        self.use_chromakey = bool(win.get("UseChromaKey", True))
        chroma = win.get("ChromaKeyColor", [0, 255, 0])
        try:
            self.chromakey_color = (int(chroma[0]), int(chroma[1]), int(chroma[2]))
        except Exception:
            self.chromakey_color = (0, 255, 0)
        self.always_on_top = bool(win.get("AlwaysOnTop", False))

        # Microphone
        mic = c.get("Microphone", {})
        self.max_v = float(mic.get("MaxVolume", 1600))
        self.background_noise = float(mic.get("BackgroundNoise", 50))
        device_idx = mic.get("DeviceIndex")
        self.device_index = int(device_idx) if device_idx is not None else None  # None = РґРµС„РѕР»С‚

        # Blink
        blink = c.get("Blink", {})
        interval = blink.get("Interval", [4, 8])
        if isinstance(interval, str):
            # РїРѕРґРґРµСЂР¶РєР° С„РѕСЂРјС‹ "0.1,3"
            try:
                a, b = [float(x.strip()) for x in interval.split(",")]
                interval = [a, b]
            except Exception:
                interval = [4, 8]
        if not (isinstance(interval, (list, tuple)) and len(interval) == 2):
            interval = [4, 8]
        self.blink_interval = (float(interval[0]), float(interval[1]))

        durations = blink.get("Durations", [0.1])
        if isinstance(durations, str):
            durations = [float(x.strip()) for x in durations.split(",") if x.strip()]
        self.blink_durations = [float(x) for x in durations] if durations else [0.1]

        # EmotionBlink
        emo = c.get("EmotionBlink", {})
        self.emo_enabled = bool(emo.get("Enabled", False))
        self.emo_threshold = float(emo.get("Threshold", 1500))
        emo_durs = emo.get("Durations", [])
        if isinstance(emo_durs, str):
            emo_durs = [float(x.strip()) for x in emo_durs.split(",") if x.strip()]
        self.emo_durations = [float(x) for x in emo_durs] if emo_durs else [0.1]

        # Movement
        move = c.get("Movement", {})
        self.jump_amp = float(move.get("JumpAmplitude", 14))
        vs = move.get("VerticalSway", [0, 0])
        hs = move.get("HorizontalSway", [0, 0])
        try:
            self.sway_v = (float(vs[0]), float(vs[1]))
        except Exception:
            self.sway_v = (0.0, 0.0)
        try:
            self.sway_h = (float(hs[0]), float(hs[1]))
        except Exception:
            self.sway_h = (0.0, 0.0)
        self.dynamic_squash_enabled = bool(move.get("DynamicSquashEnabled", True))
        self.dynamic_squash_amount = float(move.get("DynamicSquashAmount", 0.08))
        self.dynamic_squash_amount = clamp(self.dynamic_squash_amount, 0.0, 0.35)

        # Mouth
        mouth = c.get("Mouth", {})
        self.mouth_frame_interval = float(mouth.get("FrameInterval", 0.05))
        self.mouth_close_delay_enabled = bool(mouth.get("UseCloseDelay", False))
        self.mouth_close_delay = float(mouth.get("CloseDelay", 0.35))

        # LipSync improvements
        lip = c.get("LipSync", {})
        self.lip_smoothing = float(lip.get("Smoothing", 0.7))          # 0.0вЂ“1.0, С‡РµРј РІС‹С€Рµ вЂ” С‚РµРј РїР»Р°РІРЅРµРµ
        self.hyst_high = float(lip.get("HysteresisHigh", 120.0))      # РїРѕСЂРѕРі РЅР°С‡Р°Р»Р° СЂРµС‡Рё
        self.hyst_low = float(lip.get("HysteresisLow", 50.0))         # РїРѕСЂРѕРі СѓРґРµСЂР¶Р°РЅРёСЏ СЂРµС‡Рё (РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РЅРёР¶Рµ high)       

        # Debug
        self.debug = bool(c.get("DebugMode", False))
    def _configure_window(self):
        if not (IS_WINDOWS and win32gui and win32api and win32con):
            return

        try:
            self.hwnd = py.display.get_wm_info().get("window")
            if not self.hwnd:
                return

            style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)

            rect = win32gui.GetWindowRect(self.hwnd)
            self.window_pos = (rect[0], rect[1])

            if self.use_chromakey:
                win32gui.SetLayeredWindowAttributes(
                    self.hwnd,
                    win32api.RGB(*self.chromakey_color),
                    0,
                    win32con.LWA_COLORKEY,
                )
            else:
                self._init_alpha_window()

            if self.always_on_top:
                win32gui.SetWindowPos(
                    self.hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                )
        except Exception as e:
            print("Warning: failed to configure window transparency.", e)
            self.use_alpha_window = False

    def _init_alpha_window(self):
        if not (IS_WINDOWS and ctypes and self.hwnd):
            return

        width, height = self.window_size
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = width * height * 4

        screen_dc = win32gui.GetDC(0)
        bits_ptr = ctypes.c_void_p()
        self.layered_dc = win32gui.CreateCompatibleDC(screen_dc)
        self.layered_bitmap = ctypes.windll.gdi32.CreateDIBSection(
            self.layered_dc,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
            ctypes.byref(bits_ptr),
            None,
            0,
        )
        win32gui.ReleaseDC(0, screen_dc)

        if not self.layered_bitmap or not bits_ptr.value:
            raise RuntimeError("CreateDIBSection failed to create alpha buffer.")

        self.layered_bitmap_prev = win32gui.SelectObject(self.layered_dc, self.layered_bitmap)
        self.layered_bits_ptr = bits_ptr
        self.use_alpha_window = True

    def _push_alpha_frame(self, surface):
        if not self.use_alpha_window:
            return

        if not self.window_pos and self.hwnd:
            rect = win32gui.GetWindowRect(self.hwnd)
            self.window_pos = (rect[0], rect[1])

        raw = py.image.tostring(surface, "BGRA")
        ctypes.memmove(self.layered_bits_ptr.value, raw, len(raw))
        blend = (win32con.AC_SRC_OVER, 0, 255, win32con.AC_SRC_ALPHA)
        win32gui.UpdateLayeredWindow(
            self.hwnd,
            None,
            self.window_pos,
            self.window_size,
            self.layered_dc,
            (0, 0),
            0,
            blend,
            win32con.ULW_ALPHA,
        )

    # -----------------------
    # Р—Р°РіСЂСѓР·РєР° СЃРїСЂР°Р№С‚РѕРІ
    # -----------------------
    def _load_sprites(self):
        """
        Р—Р°РіСЂСѓР¶Р°РµС‚:
          - mouth_frames: s_0, s_1, ...
          - blink_frames: b_0, b_1, ...
          - emo_frames: eb_0, eb_1, ...
          - cm_frame: cm.png (closed mouth)
        Р•СЃР»Рё РєР°РєРёРµ-С‚Рѕ РіСЂСѓРїРїС‹ РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” РІС‹РґР°С‘С‚ РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ, РЅРѕ РїС‹С‚Р°РµС‚СЃСЏ РїСЂРѕРґРѕР»Р¶Р°С‚СЊ.
        """
        def load_and_scale(path):
            try:
                img = py.image.load(path).convert_alpha()
            except Exception as e:
                # Р•СЃР»Рё convert_alpha() РІСЃС‘ Р¶Рµ РїР°РґР°РµС‚ вЂ” РїСЂРѕР±СѓРµРј Р±РµР· РЅРµРіРѕ
                try:
                    img = py.image.load(path)
                except Exception as e2:
                    raise RuntimeError(f"РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ {path}: {e2}")
            # РњР°СЃС€С‚Р°Р±РёСЂРѕРІР°РЅРёРµ
            if self.scale != 1.0:
                w, h = img.get_size()
                img = py.transform.smoothscale(img, (max(1, int(w * self.scale)), max(1, int(h * self.scale))))
            # РћС‚СЂР°Р¶РµРЅРёРµ
            if self.reflect:
                img = py.transform.flip(img, True, False)
            return img

        files = sorted(os.listdir(self.sprites_path))
        self.mouth_frames = []
        self.blink_frames = []
        self.emo_frames = []
        self.cm_frame = None

        for f in files:
            name, ext = os.path.splitext(f)
            if ext.lower() not in self.SUPPORTED_EXT:
                continue
            full = os.path.join(self.sprites_path, f)
            try:
                if name.startswith("s_"):
                    self.mouth_frames.append(load_and_scale(full))
                elif name.startswith("b_"):
                    self.blink_frames.append(load_and_scale(full))
                elif name.startswith("eb_"):
                    self.emo_frames.append(load_and_scale(full))
                elif name == "cm":
                    self.cm_frame = load_and_scale(full)
            except Exception as e:
                # РќРµ РѕСЃС‚Р°РЅР°РІР»РёРІР°РµРјСЃСЏ РЅР° РїРµСЂРІРѕР№ РѕС€РёР±РєРµ Р·Р°РіСЂСѓР·РєРё РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ С„Р°Р№Р»Р°
                print(f"РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: РЅРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ {full}: {e}")

        # РџСЂРѕРІРµСЂРєРё Рё fallbacks
        if not self.mouth_frames:
            raise FileNotFoundError(f"Р’ {self.sprites_path} РЅРµ РЅР°Р№РґРµРЅС‹ РєР°РґСЂС‹ СЂС‚Р° (s_0, s_1, ...).")

        # Р•СЃР»Рё РЅРµС‚ blink_frames вЂ” СЌС‚Рѕ РЅРµ С„Р°С‚Р°Р»СЊРЅРѕ, РїСЂРѕСЃС‚Рѕ РјРѕСЂРіР°РЅРёРµ РЅРµ Р±СѓРґРµС‚
        if not self.blink_frames:
            print("РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: РєР°РґСЂС‹ РјРѕСЂРіР°РЅРёСЏ (b_*) РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” РјРѕСЂРіР°РЅРёРµ РѕС‚РєР»СЋС‡РµРЅРѕ.")

        # Р•СЃР»Рё СЌРјРѕС†РёСЏ РІРєР»СЋС‡РµРЅР°, РЅРѕ РЅРµС‚ eb вЂ” РёСЃРїРѕР»СЊР·СѓРµРј b_*
        if self.emo_enabled and not self.emo_frames:
            if self.blink_frames:
                print("РРЅС„Рѕ: СЌРјРѕС†РёРѕРЅР°Р»СЊРЅС‹Рµ РєР°РґСЂС‹ eb_* РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” РёСЃРїРѕР»СЊР·СѓРµРј b_* РґР»СЏ СЌРјРѕС†РёРё.")
                self.emo_frames = list(self.blink_frames)
                # Р•СЃР»Рё durations РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‚ вЂ” РёСЃРїРѕР»СЊР·СѓРµРј blink_durations
                if not self.emo_durations:
                    self.emo_durations = list(self.blink_durations)
            else:
                print("РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: СЌРјРѕС†РёРѕРЅР°Р»СЊРЅР°СЏ Р°РЅРёРјР°С†РёСЏ РІРєР»СЋС‡РµРЅР°, РЅРѕ РЅРµС‚ РЅРё eb_*, РЅРё b_* вЂ” СЌРјРѕС†РёСЏ РѕС‚РєР»СЋС‡РµРЅР°.")
                self.emo_enabled = False

    # -----------------------
    # РђСѓРґРёРѕ
    # -----------------------
    def _init_audio(self):
        if pyaudio is None:
            raise RuntimeError("pyaudio РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. РЈСЃС‚Р°РЅРѕРІРё pyaudio РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ РјРёРєСЂРѕС„РѕРЅРѕРј.")
        try:
            self.p = pyaudio.PyAudio()
            
            kwargs = {
                "format": pyaudio.paInt16,
                "channels": 1,
                "rate": 44100,  # СѓРЅРёС„РёС†РёСЂСѓРµРј СЃ РјРµРЅРµРґР¶РµСЂРѕРј РґР»СЏ РѕРґРёРЅР°РєРѕРІС‹С… СѓСЂРѕРІРЅРµР№ (Р±С‹Р»Рѕ 48000)
                "input": True,
                "frames_per_buffer": 1024
            }
            if self.device_index is not None:
                kwargs["input_device_index"] = self.device_index
            
            self.stream = self.p.open(**kwargs)
            time.sleep(0.05)
        except Exception as e:
            raise RuntimeError(f"РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РєСЂС‹С‚СЊ РїРѕС‚РѕРє РјРёРєСЂРѕС„РѕРЅР°: {e}")

    def _safe_read_mic(self, size_frames=1024):
        try:
            data = self.stream.read(size_frames, exception_on_overflow=False)
            numpy_data = np.frombuffer(data, dtype=np.int16).astype(np.float64)
            rms = np.sqrt(np.mean(numpy_data ** 2))
            return float(rms)
        except Exception:
            return 0.0

    # -----------------------
    # РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ СЃРѕСЃС‚РѕСЏРЅРёР№
    # -----------------------

    def _blit_centered_to(self, target_surface, img, x_offset=0, y_offset=0):
        """Р РёСЃСѓРµС‚ img, С†РµРЅС‚СЂРёСЂСѓСЏ РЅР° target_surface СЃ РѕС„С„СЃРµС‚РѕРј."""
        if img is None:
            return
        w, h = img.get_size()
        tw, th = target_surface.get_size()
        cx = (tw - w) // 2 + x_offset
        cy = (th - h) // 2 + y_offset
        target_surface.blit(img, (cx, cy))

    def apply_dynamic_squash(self, surface, intensity):
        if not self.dynamic_squash_enabled:
            return surface

        intensity = clamp(float(intensity), 0.0, 1.0)
        if intensity <= 0.001:
            return surface

        w, h = surface.get_size()
        squash_y = self.dynamic_squash_amount * intensity
        stretch_x = squash_y * 0.35
        scaled_w = int(w * (1.0 + stretch_x))
        scaled_h = int(h * (1.0 - squash_y))
        if scaled_w < 1 or scaled_h < 1:
            return surface

        scaled = py.transform.smoothscale(surface, (scaled_w, scaled_h))
        final_surf = py.Surface((w, h), py.SRCALPHA)
        offset_x = (w - scaled_w) // 2
        offset_y = (h - scaled_h) // 2 + int(h * squash_y * 0.35)
        final_surf.blit(scaled, (offset_x, offset_y))
        return final_surf


    def _init_state(self):
        self.clock = py.time.Clock()

        # Р‘Р°Р·РѕРІС‹Рµ СЃРѕСЃС‚РѕСЏРЅРёСЏ
        self.last_blink_time = time.time()
        self.blink_active = False
        self.blink_start = 0
        self.blink_frame_idx = 0

        self.emo_active = False
        self.emo_start = 0
        self.emo_frame_idx = 0

        self.last_loudness = 0.0

        self.last_mouth_frame_time = 0.0
        self.mouth_index = 0
        self.last_talk_time = time.time()

        # Р’СЂРµРјСЏ СЃС‚Р°СЂС‚Р° (РґР»СЏ sway)
        self.t0 = time.time()

        self.smoothed_loudness = 0.0
        self.was_talking = False
        self.last_raw_loudness = 0.0  # РґР»СЏ delta_l РІ СЌРјРѕС†РёРё
        self.dynamic_squash_level = 0.0
    # -----------------------
    # РџРµСЂРµРјРµС‰РµРЅРёРµ РѕРєРЅР° Р·Р° РјС‹С€СЊСЋ
    # -----------------------

    def move_window(self):
        if not IS_WINDOWS or win32api is None:
            return
        try:
            hwnd = py.display.get_wm_info().get("window")
            x, y = win32api.GetCursorPos()
            new_pos = (x - self.window_size[0] // 2, y - self.window_size[1] // 2)
            self.window_pos = new_pos
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST if self.always_on_top else 0,
                new_pos[0],
                new_pos[1],
                0,
                0,
                win32con.SWP_NOSIZE,
            )
        except Exception:
            pass

    # -----------------------
    # РћСЃРЅРѕРІРЅРѕР№ С†РёРєР»
    # -----------------------
    def run(self):
        try:
            while True:
                for event in py.event.get():
                    if event.type == py.QUIT:
                        self.exit()
                    elif event.type == py.MOUSEBUTTONDOWN:
                        while py.mouse.get_pressed()[0]:
                            py.event.pump()
                            self.move_window()

                now = time.time()

                # === РЈР›РЈР§РЁР•РќРќР«Р™ Р РђРЎР§РЃРў Р“Р РћРњРљРћРЎРўР ===
                raw_loudness = self._safe_read_mic() - self.background_noise
                raw_loudness = max(0.0, raw_loudness)

                # РЎРіР»Р°Р¶РёРІР°РЅРёРµ EMA РґР»СЏ РѕР±С‰РµР№ РіСЂРѕРјРєРѕСЃС‚Рё
                self.smoothed_loudness = (
                    self.smoothed_loudness * self.lip_smoothing +
                    raw_loudness * (1.0 - self.lip_smoothing)
                )
                loudness = clamp(self.smoothed_loudness, 0.0, self.max_v)

                # Delta РґР»СЏ СЌРјРѕС†РёРё вЂ” РЅР° raw, С‡С‚РѕР±С‹ Р»СѓС‡С€Рµ СЂРµР°РіРёСЂРѕРІР°С‚СЊ РЅР° СЂРµР·РєРёРµ РІСЃРїР»РµСЃРєРё
                delta_l = raw_loudness - self.last_raw_loudness
                self.last_raw_loudness = raw_loudness

                # Р“РёСЃС‚РµСЂРµР·РёСЃ РґР»СЏ РґРµС‚РµРєС†РёРё СЂРµС‡Рё
                if loudness > self.hyst_high:
                    talking = True
                elif loudness > self.hyst_low:
                    talking = self.was_talking
                else:
                    talking = False
                self.was_talking = talking

                if talking:
                    self.last_talk_time = now

                # === Р­РњРћР¦РРЇ ===
                if self.emo_enabled and delta_l > self.emo_threshold and not self.emo_active:
                    self.emo_active = True
                    self.emo_start = now
                    self.blink_active = False
                    self.last_blink_time = now

                if self.emo_active:
                    total = sum(self.emo_durations) if self.emo_durations else 0.0
                    if now - self.emo_start > total:
                        self.emo_active = False

                # === РњРћР Р“РђРќРР• ===
                if not self.emo_active and not self.blink_active and (now - self.last_blink_time) > random.uniform(*self.blink_interval):
                    if self.blink_frames:
                        self.blink_active = True
                        self.blink_start = now
                        self.blink_frame_idx = 0
                        self.last_blink_time = now

                if self.blink_active:
                    elapsed = now - self.blink_start
                    total = sum(self.blink_durations) if self.blink_durations else 0.0
                    if elapsed > total:
                        self.blink_active = False
                        self.blink_frame_idx = 0
                    else:
                        acc = 0.0
                        for i, d in enumerate(self.blink_durations):
                            acc += d
                            if elapsed <= acc:
                                self.blink_frame_idx = i
                                break

                # === Р РћРў ===
                if (now - self.last_mouth_frame_time) >= self.mouth_frame_interval:
                    idx = int((loudness / max(1.0, self.max_v)) * (len(self.mouth_frames) - 1))
                    self.mouth_index = clamp(idx, 0, len(self.mouth_frames) - 1)
                    self.last_mouth_frame_time = now

                target_squash = (loudness / max(1.0, self.max_v)) if talking else 0.0
                self.dynamic_squash_level = (
                    self.dynamic_squash_level * 0.8 +
                    target_squash * 0.2
                )

                # === Р”Р’РР–Р•РќРРЇ (sway + jump) ===
                elapsed_total = now - self.t0
                y_sway = self.sway_v[0] * math.sin(elapsed_total * self.sway_v[1] * 2 * math.pi) if self.sway_v[1] != 0 else 0
                x_sway = self.sway_h[0] * math.sin(elapsed_total * self.sway_h[1] * 2 * math.pi) if self.sway_h[1] != 0 else 0
                y_jump = int((loudness / max(1.0, self.max_v)) * self.jump_amp)
                y_offset = int(y_sway - y_jump)
                x_offset = int(x_sway)

                # === РћРўР РРЎРћР’РљРђ ===
                if not self.use_alpha_window:
                    self.screen.fill(self.chromakey_color if self.use_chromakey else (0, 0, 0))
                self.avatar_surface.fill((0, 0, 0, 0))  # РїСЂРѕР·СЂР°С‡РЅС‹Р№ surface РґР»СЏ Р°РІР°С‚Р°СЂР°

                # --- Р±Р°Р·РѕРІС‹Р№ СЃР»РѕР№ ---
                base_img = self.mouth_frames[0]
                self._blit_centered_to(self.avatar_surface, base_img, x_offset, -y_offset)

                # --- СЂРѕС‚ ---
                if talking:
                    self._blit_centered_to(self.avatar_surface, self.mouth_frames[self.mouth_index], x_offset, -y_offset)
                else:
                    if self.mouth_close_delay_enabled and (now - self.last_talk_time) < self.mouth_close_delay:
                        self._blit_centered_to(self.avatar_surface, self.mouth_frames[self.mouth_index], x_offset, -y_offset)
                    elif self.cm_frame:
                        self._blit_centered_to(self.avatar_surface, self.cm_frame, x_offset, -y_offset)

                # --- РіР»Р°Р·Р° ---
                if self.emo_active and self.emo_frames:
                    elapsed_e = now - self.emo_start
                    acc = 0.0
                    chosen = 0
                    for i, d in enumerate(self.emo_durations):
                        acc += d
                        if elapsed_e <= acc:
                            chosen = i
                            break
                    chosen = clamp(chosen, 0, len(self.emo_frames) - 1)
                    self._blit_centered_to(self.avatar_surface, self.emo_frames[chosen], x_offset, -y_offset)
                elif self.blink_active and self.blink_frames:
                    idx = clamp(self.blink_frame_idx, 0, len(self.blink_frames) - 1)
                    self._blit_centered_to(self.avatar_surface, self.blink_frames[idx], x_offset, -y_offset)

                # --- dynamic squash ---
                final_avatar = self.apply_dynamic_squash(self.avatar_surface.copy(), self.dynamic_squash_level)

                # --- РІС‹РІРѕРґ РЅР° СЌРєСЂР°РЅ ---
                if self.use_alpha_window:
                    self._push_alpha_frame(final_avatar)
                else:
                    self.screen.blit(final_avatar, (0, 0))
                    py.display.update()
                self.clock.tick(60)

                # --- РѕС‚Р»Р°РґРѕС‡РЅС‹Р№ РІС‹РІРѕРґ ---
                if self.debug:
                    print(f"raw={raw_loudness:5.0f} smooth={loudness:5.0f} d={delta_l:5.0f} "
                        f"mouth={self.mouth_index} talk={talking} emo={self.emo_active} "
                        f"blink={self.blink_active}", end="\r")

        except KeyboardInterrupt:
            self.exit()
        except Exception as e:
            show_console()
            print("РћС€РёР±РєР° РІ РѕСЃРЅРѕРІРЅРѕРј С†РёРєР»Рµ:", e)
            traceback.print_exc()
            self.exit()

    # -----------------------
    # Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅС‹Рµ
    # -----------------------
    def _blit_centered(self, img, x_offset=0, y_offset=0):
        """
        Р РёСЃСѓРµС‚ РёР·РѕР±СЂР°Р¶РµРЅРёРµ, С†РµРЅС‚СЂРёСЂСѓСЏ РµРіРѕ РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ РѕРєРЅР° Рё СЃРґРІРёРіР°СЏ РЅР° x_offset,y_offset.
        y_offset РѕС‚СЂР°Р¶Р°РµС‚ РІРµСЂС‚РёРєР°Р»СЊРЅРѕРµ СЃРјРµС‰РµРЅРёРµ (РїРѕР»РѕР¶РёС‚РµР»СЊРЅРѕРµ вЂ” РІРЅРёР·), РІ РєРѕРґРµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ -y_offset РґР»СЏ "РїРѕРґРїСЂС‹РіРёРІР°РЅРёСЏ".
        """
        if img is None:
            return
        w, h = img.get_size()
        cx = (self.window_size[0] - w) // 2 + x_offset
        cy = (self.window_size[1] - h) // 2 + y_offset
        self.screen.blit(img, (cx, cy))

    # -----------------------
    # Р—Р°РІРµСЂС€РµРЅРёРµ
    # -----------------------
    def exit(self):
        try:
            if hasattr(self, "stream") and self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception:
                    pass
            if hasattr(self, "p") and self.p:
                try:
                    self.p.terminate()
                except Exception:
                    pass
            if self.layered_dc and self.layered_bitmap_prev:
                try:
                    win32gui.SelectObject(self.layered_dc, self.layered_bitmap_prev)
                except Exception:
                    pass
            if self.layered_bitmap:
                try:
                    win32gui.DeleteObject(self.layered_bitmap)
                except Exception:
                    pass
            if self.layered_dc:
                try:
                    win32gui.DeleteDC(self.layered_dc)
                except Exception:
                    pass
        finally:
            try:
                py.quit()
            except Exception:
                pass
            # Р•СЃР»Рё РјС‹ РІ РѕС‚Р»Р°РґРѕС‡РЅРѕРј СЂРµР¶РёРјРµ вЂ” РѕСЃС‚Р°РІРёРј РєРѕРЅСЃРѕР»СЊ РѕС‚РєСЂС‹С‚РѕР№, РёРЅР°С‡Рµ РїРѕРїС‹С‚Р°РµРјСЃСЏ Р·Р°РєСЂС‹С‚СЊ
            if not self.debug:
                hide_console()
            sys.exit(0)


# -----------------------
# РўРѕС‡РєР° РІС…РѕРґР°
# -----------------------
def main():
    if len(sys.argv) < 2:
        show_console()
        print("РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ: python avatar.py [РёРјСЏ_РїСЂРµСЃРµС‚Р°]")
        print("РџСЂРёРјРµСЂ: python avatar.py Slipper")
        sys.exit(1)

    preset = sys.argv[1]
    try:
        avatar = Avatar(preset)
    except Exception as e:
        show_console()
        print("РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ Avatar:", e)
        traceback.print_exc()
        sys.exit(1)

    avatar.run()


if __name__ == "__main__":
    main()




