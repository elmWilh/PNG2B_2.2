#!/usr/bin/env python3
# avatar.py
# Запуск: python avatar.py [preset_name]
# Загружает пресет из папки presets/ и запускает анимированного аватара.

import os
import sys
import json
import time
import math
import random
import traceback
from app_meta import APP_WINDOW_TITLE
from app_paths import LEGACY_PRESET_DIRS, PRESET_AVATAR_DIR, PRESET_CONFIG_NAME, PRESET_EMOTIONS_DIR, PRESET_RUNTIME_CONTROL_NAME

# Импортируем pygame и numpy/pyaudio; оставляем понятные ошибки на случай отсутствия библиотек.
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
    pyaudio = None  # Проверим позже и завершимся с понятным сообщением.

# Для управления окном на Windows.
IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes
        import win32api
        import win32gui
        import win32.lib.win32con as win32con
    except Exception:
        # Если win32 недоступен, продолжаем без AlwaysOnTop/Layered-функций.
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
# Утилиты
# -----------------------
def show_console():
    """Показать консоль на Windows."""
    if IS_WINDOWS and ctypes:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)


def hide_console():
    """Скрыть консоль на Windows."""
    if IS_WINDOWS and ctypes:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)


def load_json_safe(path):
    """Загружает JSON и возвращает dict либо выбрасывает понятное исключение."""
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

    def __init__(self, preset_name: str, presets_dirs=LEGACY_PRESET_DIRS):
        self.preset_name = preset_name
        self.presets_dirs = presets_dirs

        # Ищем каталог пресета; сначала новая структура, затем legacy-папки.
        self.preset_path = None
        for d in self.presets_dirs:
            candidate = os.path.join(d, preset_name)
            if os.path.isdir(candidate):
                self.preset_path = candidate
                break

        if not self.preset_path:
            raise FileNotFoundError(f"РќРµ РЅР°Р№РґРµРЅ РїСЂРµСЃРµС‚ '{preset_name}' РІ РїР°РїРєР°С… {presets_dirs}")

        # Основные пути внутри пресета.
        self.config_path = os.path.join(self.preset_path, PRESET_CONFIG_NAME)
        self.sprites_path = os.path.join(self.preset_path, PRESET_AVATAR_DIR)
        self.emotions_path = os.path.join(self.preset_path, PRESET_EMOTIONS_DIR)
        self.runtime_control_path = os.path.join(self.preset_path, PRESET_RUNTIME_CONTROL_NAME)

        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(f"{PRESET_CONFIG_NAME} РЅРµ РЅР°Р№РґРµРЅ РІ {self.preset_path}")
        if not os.path.isdir(self.sprites_path):
            raise FileNotFoundError(f"РџР°РїРєР° {PRESET_AVATAR_DIR} РЅРµ РЅР°Р№РґРµРЅР° РІ {self.preset_path}")

        # Загружаем конфиг; валидация и нормализация идут ниже.
        self.config = load_json_safe(self.config_path)

        # Разбираем конфиг и заполняем недостающие значения.
        self._parse_config()

        # Инициализируем Pygame display до загрузки изображений.
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

        # Создаём окно до загрузки спрайтов; это нужно для .convert_alpha().
        self.screen = py.display.set_mode(self.window_size, py.NOFRAME)
        py.display.set_caption(f"{APP_WINDOW_TITLE} - {self.preset_name}")

        self._configure_window()

        self._load_sprites()

        # Инициализируем аудио и микрофон.
        self._init_audio()

        # Подготавливаем служебное состояние для анимаций.
        self._init_state()
        self._init_runtime_state()
        self.avatar_surface = py.Surface(self.window_size, py.SRCALPHA)

        # В режиме отладки оставляем консоль, иначе скрываем её.
        if not self.debug:
            hide_console()
        else:
            show_console()

    # -----------------------
    # Парсинг конфига и значения по умолчанию
    # -----------------------
    def _parse_config(self):
        c = self.config

        # Window
        win = c.get("Window", {})
        size = win.get("Size", [750])
        if not isinstance(size, (list, tuple)):
            # Поддерживаем старый формат с одним числом.
            size = [size]
        if len(size) == 1:
            self.window_size = (max(1, int(size[0])), max(1, int(size[0])))
        else:
            self.window_size = (max(1, int(size[0])), max(1, int(size[1])))

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
        self.device_index = int(device_idx) if device_idx is not None else None  # None = устройство по умолчанию

        # Blink
        blink = c.get("Blink", {})
        interval = blink.get("Interval", [4, 8])
        if isinstance(interval, str):
            # Поддержка старого строкового формата "0.1,3".
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
        mode = str(move.get("Mode", "")).strip().capitalize()
        if mode not in {"Squash", "Bounce", "Static"}:
            mode = "Squash" if bool(move.get("DynamicSquashEnabled", True)) else "Bounce"
        self.movement_mode = mode
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
        self.dynamic_squash_enabled = self.movement_mode == "Squash"
        self.dynamic_squash_amount = float(move.get("DynamicSquashAmount", 0.08))
        self.dynamic_squash_amount = clamp(self.dynamic_squash_amount, 0.0, 0.35)

        petpet = c.get("PetPet", {})
        self.petpet_enabled = bool(petpet.get("Enabled", True))
        self.petpet_amplitude = clamp(float(petpet.get("Amplitude", 0.12)), 0.0, 0.45)
        self.petpet_cycle_duration = max(0.15, float(petpet.get("CycleDuration", 0.45)))
        self.petpet_hand_offset_x = float(petpet.get("HandOffsetX", 0.0))
        self.petpet_hand_offset_y = float(petpet.get("HandOffsetY", 0.0))
        self.petpet_hand_scale = max(0.1, float(petpet.get("HandScale", 1.0)))
        self.petpet_frame_count = max(1, int(petpet.get("FrameCount", 5)))
        self.petpet_event_duration = max(0.2, float(petpet.get("EventDuration", 2.0)))

        # Mouth
        mouth = c.get("Mouth", {})
        self.mouth_frame_interval = float(mouth.get("FrameInterval", 0.05))
        self.mouth_close_delay_enabled = bool(mouth.get("UseCloseDelay", False))
        self.mouth_close_delay = float(mouth.get("CloseDelay", 0.35))

        # Улучшения LipSync
        lip = c.get("LipSync", {})
        self.lip_smoothing = float(lip.get("Smoothing", 0.7))          # 0.0-1.0: чем выше, тем плавнее реакция.
        self.hyst_high = float(lip.get("HysteresisHigh", 120.0))      # Порог начала речи.
        self.hyst_low = float(lip.get("HysteresisLow", 50.0))         # Порог удержания речи; должен быть ниже high.

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

    def _default_runtime_control(self):
        return {
            "debug_visible": bool(self.debug),
            "events": {
                "petpet_live": False,
                "reaction_live": False,
                "selected_reaction": "",
            },
            "commands": {
                "force_blink": 0.0,
                "force_emotion": 0.0,
                "trigger_petpet": 0.0,
                "trigger_reaction": 0.0,
            },
        }

    def _init_runtime_state(self):
        self.runtime_poll_interval = 0.2
        self.last_runtime_poll = 0.0
        self.last_runtime_command_marks = {}
        self.petpet_live_enabled = False
        self.selected_reaction = ""
        self.petpet_event_until = 0.0
        self.petpet_event_started = 0.0
        if not hasattr(self, "petpet_frames"):
            self.petpet_frames = []
        self._apply_runtime_control(self._load_runtime_control())

    def _load_runtime_control(self):
        control = self._default_runtime_control()
        if not os.path.isfile(self.runtime_control_path):
            return control

        try:
            with open(self.runtime_control_path, "r", encoding="utf-8") as file:
                raw = json.load(file)
        except Exception:
            return control

        raw_events = raw.get("events", {})
        control["debug_visible"] = bool(raw.get("debug_visible", control["debug_visible"]))
        control["events"]["petpet_live"] = bool(raw_events.get("petpet_live", False))
        control["events"]["reaction_live"] = bool(raw_events.get("reaction_live", control["events"]["petpet_live"]))
        selected_reaction = str(raw_events.get("selected_reaction", "")).strip().lower()
        if not selected_reaction and (
            control["events"]["reaction_live"] or control["events"]["petpet_live"]
        ):
            selected_reaction = "petpet"
        control["events"]["selected_reaction"] = selected_reaction
        raw_commands = raw.get("commands", {})
        for key in control["commands"]:
            try:
                legacy_key = "trigger_petpet" if key == "trigger_reaction" else key
                control["commands"][key] = float(raw_commands.get(key, raw_commands.get(legacy_key, 0.0)))
            except Exception:
                control["commands"][key] = 0.0
        return control

    def _apply_runtime_control(self, control, now=None):
        if now is None:
            now = time.time()

        events = control.get("events", {})
        self.selected_reaction = str(events.get("selected_reaction", "")).strip().lower()
        self.petpet_live_enabled = bool(events.get("reaction_live", events.get("petpet_live", False))) and self.selected_reaction == "petpet"

        debug_visible = bool(control.get("debug_visible", self.debug))
        self.debug = debug_visible
        if self.debug:
            show_console()
        else:
            hide_console()

        commands = control.get("commands", {})
        self._consume_runtime_command(commands, "force_blink", lambda: self._trigger_blink(now))
        self._consume_runtime_command(commands, "force_emotion", lambda: self._trigger_emotion(now))
        self._consume_runtime_command(commands, "trigger_petpet", lambda: self._trigger_petpet(now))
        self._consume_runtime_command(commands, "trigger_reaction", lambda: self._trigger_selected_reaction(now))

    def _consume_runtime_command(self, commands, key, callback):
        try:
            marker = float(commands.get(key, 0.0))
        except Exception:
            marker = 0.0

        if marker <= 0.0:
            return
        if self.last_runtime_command_marks.get(key) == marker:
            return

        self.last_runtime_command_marks[key] = marker
        callback()

    def _poll_runtime_control(self, now):
        if (now - self.last_runtime_poll) < self.runtime_poll_interval:
            return
        self.last_runtime_poll = now
        self._apply_runtime_control(self._load_runtime_control(), now=now)

    def _trigger_blink(self, now):
        if not self.blink_frames:
            return
        self.emo_active = False
        self.blink_active = True
        self.blink_start = now
        self.blink_frame_idx = 0
        self.last_blink_time = now

    def _trigger_emotion(self, now):
        if not self.emo_frames and self.blink_frames:
            self.emo_frames = list(self.blink_frames)
            if not self.emo_durations:
                self.emo_durations = list(self.blink_durations)
        if not self.emo_frames:
            return
        self.blink_active = False
        self.emo_active = True
        self.emo_start = now
        self.last_blink_time = now

    def _trigger_selected_reaction(self, now):
        if self.selected_reaction == "petpet":
            self._trigger_petpet(now)

    def _trigger_petpet(self, now):
        if not self.petpet_frames:
            self._load_petpet_sprite()
        if not self.petpet_enabled or not self.petpet_frames:
            return
        self.selected_reaction = "petpet"
        self.petpet_event_started = now
        self.petpet_event_until = max(self.petpet_event_until, now + self.petpet_event_duration)

    # -----------------------
    # Загрузка спрайтов
    # -----------------------
    def _transform_sprite(self, img):
        if img is None:
            return None

        transformed = img
        if self.reflect:
            transformed = py.transform.flip(transformed, True, False)

        return transformed

    def _fit_sprite_groups(self):
        all_frames = []
        for frames in (self.mouth_frames, self.blink_frames, self.emo_frames):
            all_frames.extend(frame for frame in frames if frame is not None)
        if self.cm_frame is not None:
            all_frames.append(self.cm_frame)

        if not all_frames:
            return

        max_w = max(frame.get_width() for frame in all_frames)
        max_h = max(frame.get_height() for frame in all_frames)
        if max_w < 1 or max_h < 1:
            return

        fit_scale = min(self.window_size[0] / max_w, self.window_size[1] / max_h)
        final_scale = max(0.01, fit_scale * self.scale)

        def scale_frame(frame):
            if frame is None:
                return None
            target_w = max(1, int(round(frame.get_width() * final_scale)))
            target_h = max(1, int(round(frame.get_height() * final_scale)))
            if (target_w, target_h) == frame.get_size():
                return frame
            return py.transform.smoothscale(frame, (target_w, target_h))

        self.mouth_frames = [scale_frame(frame) for frame in self.mouth_frames]
        self.blink_frames = [scale_frame(frame) for frame in self.blink_frames]
        self.emo_frames = [scale_frame(frame) for frame in self.emo_frames]
        self.cm_frame = scale_frame(self.cm_frame)

    def _resolve_petpet_sprite_path(self):
        candidate = os.path.join(self.emotions_path, "petpet", "sprite.png")
        if os.path.isfile(candidate):
            return candidate

        legacy_path = os.path.join(self.sprites_path, "PetPet", "sprite.png")
        if os.path.isfile(legacy_path):
            return legacy_path
        root_path = "sprite.png"
        if os.path.isfile(root_path):
            return root_path
        return None

    def _load_petpet_sprite(self):
        self.petpet_frames = []
        petpet_path = self._resolve_petpet_sprite_path()
        if not petpet_path:
            return

        try:
            sprite = py.image.load(petpet_path).convert_alpha()
        except Exception:
            try:
                sprite = py.image.load(petpet_path)
            except Exception:
                return

        sprite = self._transform_sprite(sprite)
        width, height = sprite.get_size()
        frame_count = max(1, self.petpet_frame_count)
        frame_width = width // frame_count
        if frame_width < 1 or height < 1:
            return

        for index in range(frame_count):
            rect = py.Rect(index * frame_width, 0, frame_width, height)
            if rect.right > width:
                break
            frame = py.Surface((rect.width, rect.height), py.SRCALPHA)
            frame.blit(sprite, (0, 0), rect)
            self.petpet_frames.append(frame)

    def _is_petpet_active(self, now):
        return self.petpet_enabled and bool(self.petpet_frames) and (
            self.petpet_live_enabled or self.petpet_event_until > now
        )

    def _petpet_frame_state(self, now):
        if not self._is_petpet_active(now):
            return None

        elapsed = max(0.0, now - (self.petpet_event_started if self.petpet_event_started > 0 else now))
        if self.petpet_live_enabled:
            elapsed = max(0.0, now - self.t0)
        cycle_progress = (elapsed % self.petpet_cycle_duration) / self.petpet_cycle_duration
        frame_index = int(cycle_progress * len(self.petpet_frames)) % len(self.petpet_frames)
        frame = self.petpet_frames[frame_index]

        avatar_scales = (
            (1.00, 1.00, 0.00, 0.00),
            (1.03, 0.94, 0.00, 0.02),
            (1.07, 0.84, 0.00, 0.08),
            (1.04, 0.90, 0.00, 0.04),
            (1.00, 1.00, 0.00, 0.00),
        )
        hand_offsets = (
            (0.10, 0.02),
            (0.09, -0.01),
            (0.08, -0.04),
            (0.09, -0.01),
            (0.10, 0.02),
        )
        scale_x, scale_y, offset_x_ratio, offset_y_ratio = avatar_scales[frame_index % len(avatar_scales)]
        hand_offset_x_ratio, hand_offset_y_ratio = hand_offsets[frame_index % len(hand_offsets)]
        scale_y = max(0.55, 1.0 - ((1.0 - scale_y) * (self.petpet_amplitude / 0.12 if self.petpet_amplitude > 0 else 0.0)))
        scale_x = max(0.7, 1.0 + ((scale_x - 1.0) * (self.petpet_amplitude / 0.12 if self.petpet_amplitude > 0 else 0.0)))

        return {
            "frame": frame,
            "index": frame_index,
            "avatar_scale_x": scale_x,
            "avatar_scale_y": scale_y,
            "avatar_offset_x": offset_x_ratio,
            "avatar_offset_y": offset_y_ratio,
            "hand_offset_x": hand_offset_x_ratio,
            "hand_offset_y": hand_offset_y_ratio,
        }

    def _apply_petpet_overlay(self, surface, now):
        state = self._petpet_frame_state(now)
        if state is None:
            return surface

        bounds = surface.get_bounding_rect()
        if bounds.width < 1 or bounds.height < 1:
            return surface

        avatar = py.Surface((bounds.width, bounds.height), py.SRCALPHA)
        avatar.blit(surface, (0, 0), bounds)
        scaled_avatar = py.transform.smoothscale(
            avatar,
            (
                max(1, int(round(bounds.width * state["avatar_scale_x"]))),
                max(1, int(round(bounds.height * state["avatar_scale_y"]))),
            ),
        )

        overlay = py.Surface(surface.get_size(), py.SRCALPHA)
        avatar_x = bounds.x + (bounds.width - scaled_avatar.get_width()) // 2 + int(surface.get_width() * state["avatar_offset_x"])
        avatar_y = bounds.y + (bounds.height - scaled_avatar.get_height()) // 2 + int(surface.get_height() * state["avatar_offset_y"])
        overlay.blit(scaled_avatar, (avatar_x, avatar_y))

        hand = state["frame"]
        target_hand_w = max(1, int(bounds.width * 0.62 * self.petpet_hand_scale))
        target_hand_h = max(1, int(bounds.height * 0.32 * self.petpet_hand_scale))
        hand_scale = min(target_hand_w / hand.get_width(), target_hand_h / hand.get_height())
        hand_size = (
            max(1, int(round(hand.get_width() * hand_scale))),
            max(1, int(round(hand.get_height() * hand_scale))),
        )
        hand = py.transform.smoothscale(hand, hand_size)

        hand_x = int(
            bounds.x + (bounds.width - hand.get_width()) / 2
            + bounds.width * state["hand_offset_x"]
            + self.petpet_hand_offset_x
        )
        hand_y = int(
            bounds.y - hand.get_height() * 0.12
            + bounds.height * state["hand_offset_y"]
            + self.petpet_hand_offset_y
        )
        overlay.blit(hand, (hand_x, hand_y))
        return overlay

    def _load_sprites(self):
        """
        Загружает:
          - mouth_frames: s_0, s_1, ...
          - blink_frames: b_0, b_1, ...
          - emo_frames: eb_0, eb_1, ...
          - cm_frame: cm.png (закрытый рот)

        Если какая-то группа не найдена, печатает предупреждение и пытается продолжить работу.
        """
        def load_sprite(path):
            try:
                img = py.image.load(path).convert_alpha()
            except Exception as e:
                # Если convert_alpha() не сработал, пробуем без него.
                try:
                    img = py.image.load(path)
                except Exception as e2:
                    raise RuntimeError(f"РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ {path}: {e2}")
            return self._transform_sprite(img)

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
                    self.mouth_frames.append(load_sprite(full))
                elif name.startswith("b_"):
                    self.blink_frames.append(load_sprite(full))
                elif name.startswith("eb_"):
                    self.emo_frames.append(load_sprite(full))
                elif name == "cm":
                    self.cm_frame = load_sprite(full)
            except Exception as e:
                # Не падаем на первой ошибке загрузки конкретного файла.
                print(f"РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: РЅРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ {full}: {e}")

        # Проверки и fallback-сценарии.
        if not self.mouth_frames:
            raise FileNotFoundError(f"Р’ {self.sprites_path} РЅРµ РЅР°Р№РґРµРЅС‹ РєР°РґСЂС‹ СЂС‚Р° (s_0, s_1, ...).")

        # Если blink_frames нет, это не фатально: просто отключаем моргание.
        if not self.blink_frames:
            print("РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: РєР°РґСЂС‹ РјРѕСЂРіР°РЅРёСЏ (b_*) РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” РјРѕСЂРіР°РЅРёРµ РѕС‚РєР»СЋС‡РµРЅРѕ.")

        # Если эмоциональная анимация включена, но eb_* нет, пробуем использовать b_*.
        if self.emo_enabled and not self.emo_frames:
            if self.blink_frames:
                print("РРЅС„Рѕ: СЌРјРѕС†РёРѕРЅР°Р»СЊРЅС‹Рµ РєР°РґСЂС‹ eb_* РЅРµ РЅР°Р№РґРµРЅС‹ вЂ” РёСЃРїРѕР»СЊР·СѓРµРј b_* РґР»СЏ СЌРјРѕС†РёРё.")
                self.emo_frames = list(self.blink_frames)
                # Если durations отсутствуют, используем blink_durations.
                if not self.emo_durations:
                    self.emo_durations = list(self.blink_durations)
            else:
                print("РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ: СЌРјРѕС†РёРѕРЅР°Р»СЊРЅР°СЏ Р°РЅРёРјР°С†РёСЏ РІРєР»СЋС‡РµРЅР°, РЅРѕ РЅРµС‚ РЅРё eb_*, РЅРё b_* вЂ” СЌРјРѕС†РёСЏ РѕС‚РєР»СЋС‡РµРЅР°.")
                self.emo_enabled = False

        self._fit_sprite_groups()
        self._load_petpet_sprite()

    # -----------------------
    # Аудио
    # -----------------------
    def _init_audio(self):
        if pyaudio is None:
            raise RuntimeError("pyaudio РЅРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅ. РЈСЃС‚Р°РЅРѕРІРё pyaudio РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ РјРёРєСЂРѕС„РѕРЅРѕРј.")
        try:
            self.p = pyaudio.PyAudio()
            
            kwargs = {
                "format": pyaudio.paInt16,
                "channels": 1,
                "rate": 44100,  # Держим тот же rate, что и в менеджере, для одинакового уровня.
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
    # Инициализация состояния
    # -----------------------

    def _blit_centered_to(self, target_surface, img, x_offset=0, y_offset=0):
        """Рисует изображение по центру target_surface с указанным смещением."""
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

        # Базовые состояния.
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

        # Время старта для sway-анимации.
        self.t0 = time.time()

        self.smoothed_loudness = 0.0
        self.was_talking = False
        self.last_raw_loudness = 0.0  # Нужно для вычисления delta_l в эмоциональной анимации.
        self.dynamic_squash_level = 0.0
    # -----------------------
    # Перемещение окна мышью
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
    # Основной цикл
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
                self._poll_runtime_control(now)

                # === Расчёт громкости ===
                raw_loudness = self._safe_read_mic() - self.background_noise
                raw_loudness = max(0.0, raw_loudness)

                # EMA-сглаживание общей громкости.
                self.smoothed_loudness = (
                    self.smoothed_loudness * self.lip_smoothing +
                    raw_loudness * (1.0 - self.lip_smoothing)
                )
                loudness = clamp(self.smoothed_loudness, 0.0, self.max_v)

                # Delta считаем по raw, чтобы лучше ловить резкие всплески.
                delta_l = raw_loudness - self.last_raw_loudness
                self.last_raw_loudness = raw_loudness

                # Гистерезис для определения факта речи.
                if loudness > self.hyst_high:
                    talking = True
                elif loudness > self.hyst_low:
                    talking = self.was_talking
                else:
                    talking = False
                self.was_talking = talking

                if talking:
                    self.last_talk_time = now

                # === Эмоция ===
                if self.emo_enabled and delta_l > self.emo_threshold and not self.emo_active:
                    self.emo_active = True
                    self.emo_start = now
                    self.blink_active = False
                    self.last_blink_time = now

                if self.emo_active:
                    total = sum(self.emo_durations) if self.emo_durations else 0.0
                    if now - self.emo_start > total:
                        self.emo_active = False

                # === Моргание ===
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

                # === Рот ===
                if (now - self.last_mouth_frame_time) >= self.mouth_frame_interval:
                    idx = int((loudness / max(1.0, self.max_v)) * (len(self.mouth_frames) - 1))
                    self.mouth_index = clamp(idx, 0, len(self.mouth_frames) - 1)
                    self.last_mouth_frame_time = now

                speech_intensity = (loudness / max(1.0, self.max_v)) if talking else 0.0
                target_squash = speech_intensity if self.movement_mode == "Squash" else 0.0
                self.dynamic_squash_level = (
                    self.dynamic_squash_level * 0.8 +
                    target_squash * 0.2
                )

                # === Движение (sway + jump) ===
                elapsed_total = now - self.t0
                movement_enabled = self.movement_mode != "Static"
                y_sway = self.sway_v[0] * math.sin(elapsed_total * self.sway_v[1] * 2 * math.pi) if movement_enabled and self.sway_v[1] != 0 else 0
                x_sway = self.sway_h[0] * math.sin(elapsed_total * self.sway_h[1] * 2 * math.pi) if movement_enabled and self.sway_h[1] != 0 else 0
                y_jump = int(speech_intensity * self.jump_amp) if self.movement_mode == "Bounce" else 0
                y_offset = int(y_sway - y_jump)
                x_offset = int(x_sway)

                # === Отрисовка ===
                if not self.use_alpha_window:
                    self.screen.fill(self.chromakey_color if self.use_chromakey else (0, 0, 0))
                self.avatar_surface.fill((0, 0, 0, 0))  # Прозрачная поверхность для сборки аватара.

                # --- Базовый слой ---
                base_img = self.mouth_frames[0]
                self._blit_centered_to(self.avatar_surface, base_img, x_offset, -y_offset)

                # --- Рот ---
                if talking:
                    self._blit_centered_to(self.avatar_surface, self.mouth_frames[self.mouth_index], x_offset, -y_offset)
                else:
                    if self.mouth_close_delay_enabled and (now - self.last_talk_time) < self.mouth_close_delay:
                        self._blit_centered_to(self.avatar_surface, self.mouth_frames[self.mouth_index], x_offset, -y_offset)
                    elif self.cm_frame:
                        self._blit_centered_to(self.avatar_surface, self.cm_frame, x_offset, -y_offset)

                # --- Глаза ---
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
                final_avatar = self._apply_petpet_overlay(final_avatar, now)

                # --- Вывод на экран ---
                if self.use_alpha_window:
                    self._push_alpha_frame(final_avatar)
                else:
                    self.screen.blit(final_avatar, (0, 0))
                    py.display.update()
                self.clock.tick(60)

                # --- Отладочный вывод ---
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
    # Вспомогательные методы
    # -----------------------
    def _blit_centered(self, img, x_offset=0, y_offset=0):
        """
        Рисует изображение по центру окна со смещением x_offset/y_offset.
        Положительный y_offset смещает изображение вниз.
        """
        if img is None:
            return
        w, h = img.get_size()
        cx = (self.window_size[0] - w) // 2 + x_offset
        cy = (self.window_size[1] - h) // 2 + y_offset
        self.screen.blit(img, (cx, cy))

    # -----------------------
    # Завершение работы
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
            # В debug-режиме консоль оставляем открытой, иначе стараемся скрыть.
            if not self.debug:
                hide_console()
            sys.exit(0)


# -----------------------
# Точка входа
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




