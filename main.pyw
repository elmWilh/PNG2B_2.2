import os
import sys
import json
import shutil
import threading
import numpy as np
import pyaudio
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QPushButton, QWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QMessageBox, QLabel, QInputDialog,
    QComboBox, QProgressBar, QScrollArea
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QObject, pyqtSignal

PRISSETS_DIR = "Prissets"
ICON_PATH = "PNG2B.ico"
# Логичный порядок категорий: сначала окно и микрофон, потом улучшения аудио (LipSync), затем анимации
CATEGORY_ORDER = ["Window", "Microphone", "LipSync", "Blink", "EmotionBlink", "Movement", "Mouth"]


def repair_text(text):
    if isinstance(text, bytes):
        for encoding in ("utf-8", "cp1251", "cp866", "mbcs"):
            try:
                text = text.decode(encoding)
                break
            except Exception:
                continue
        else:
            text = text.decode("utf-8", errors="replace")

    text = str(text)
    if not any(marker in text for marker in ("Р", "С", "Ѓ", "Џ", "вЂ", "â")):
        return text

    candidates = [text]
    for source_encoding in ("cp1251", "latin1", "cp866"):
        try:
            candidates.append(text.encode(source_encoding).decode("utf-8"))
        except Exception:
            pass

    def score(value):
        suspicious = sum(value.count(ch) for ch in ("Р", "С", "Ѓ", "Џ", "вЂ", "â"))
        cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04FF")
        replacement = value.count("\ufffd")
        return (cyrillic - suspicious * 2 - replacement * 4, -suspicious, -replacement, -len(value))

    return max(candidates, key=score)


class MicMonitor(QObject):
    level_changed = pyqtSignal(int)

    def __init__(self, device_index=0):
        super().__init__()
        self.device_index = device_index
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False

    def _run(self):
        p = pyaudio.PyAudio()
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=44100,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=1024
            )
            while self.running:
                data = stream.read(1024, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16)
                try:
                    level = int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                    if np.isnan(level):
                        level = 0
                except:
                    level = 0
                self.level_changed.emit(level)
            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()


class PresetManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_data = {}
        self.config_fields = {}
        self.mic_monitor = None
        self.process = None

        self.setWindowTitle("PNG2B v2.2 - Avatar Preset Manager")
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1000, 600)

        self.unsaved_label = QLabel("●")
        self.unsaved_label.setStyleSheet("color: green; font-size: 18px;")
        self.unsaved_label.setToolTip("● Зеленый — сохранено\n● Красный — есть несохранённые изменения")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Left panel - preset list and buttons
        self.preset_list = QListWidget()
        self.preset_list.itemClicked.connect(self.load_config)
        self.preset_list.itemDoubleClicked.connect(self.rename_preset)

        self.btn_create = QPushButton("Создать")
        self.btn_copy = QPushButton("Копировать")
        self.btn_delete = QPushButton("Удалить")
        self.btn_open = QPushButton("Открыть папку")
        self.btn_run = QPushButton("Запустить")
        self.btn_stop = QPushButton("Остановить")
        self.btn_save = QPushButton("Сохранить")

        self.btn_create.clicked.connect(self.create_preset)
        self.btn_copy.clicked.connect(self.copy_preset)
        self.btn_delete.clicked.connect(self.delete_preset)
        self.btn_open.clicked.connect(self.open_folder)
        self.btn_run.clicked.connect(self.run_avatar)
        self.btn_stop.clicked.connect(self.stop_avatar)
        self.btn_save.clicked.connect(self.save_config)

        btn_layout = QHBoxLayout()
        for b in (self.btn_create, self.btn_copy, self.btn_delete,
                  self.btn_open, self.btn_run, self.btn_stop,
                  self.btn_save, self.unsaved_label):
            btn_layout.addWidget(b)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Пресеты"))
        left_layout.addWidget(self.preset_list)
        left_layout.addLayout(btn_layout)

        # Right panel - config form with scroll
        self.config_form = QFormLayout()
        self.config_form.setLabelAlignment(Qt.AlignRight)
        self.config_form.setFormAlignment(Qt.AlignLeft)
        self.config_form.setVerticalSpacing(8)

        config_widget = QWidget()
        config_widget.setLayout(self.config_form)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(config_widget)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, 1)
        main_layout.addWidget(scroll_area, 3)  # больше места под настройки
        main_widget.setLayout(main_layout)

        self.load_presets()
        self.set_unsaved(False)

    # ---------------- Lifecycle ----------------
    def closeEvent(self, event):
        if self.mic_monitor:
            self.mic_monitor.stop()
            self.mic_monitor = None
        if self.process:
            self.process.terminate()
            self.process = None
        event.accept()

    # ---------------- Unsaved indicator ----------------
    def set_unsaved(self, value=True):
        self.unsaved = value
        self.unsaved_label.setStyleSheet(
            f"color: {'red' if value else 'green'}; font-size: 18px;"
        )

    # ---------------- Microphone helpers ----------------
    def list_microphones(self):
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                name = repair_text(info.get("name", f"Input Device {i}"))
                devices.append((i, name))
        p.terminate()
        return devices

    def add_microphone_widgets(self):
        if hasattr(self, "mic_combo"):
            return

        self.mic_combo = QComboBox()
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 5000)  # увеличил диапазон для лучшей визуализации
        self.mic_level.setTextVisible(True)
        self.mic_level.setFormat("%v")

        self.mics = self.list_microphones()
        for idx, name in self.mics:
            self.mic_combo.addItem(name, idx)

        self.mic_combo.currentIndexChanged.connect(self.restart_microphone)

        self.config_form.addRow(QLabel("<b>Устройство микрофона</b>"), self.mic_combo)
        self.config_form.addRow(QLabel("Уровень микрофона"), self.mic_level)

        self.start_microphone()

    def start_microphone(self):
        if not hasattr(self, "mic_combo"):
            return
        device_index = self.mic_combo.currentData()
        if device_index is None:
            return

        if self.mic_monitor:
            self.mic_monitor.stop()

        self.mic_monitor = MicMonitor(device_index)
        self.mic_monitor.level_changed.connect(self.mic_level.setValue)
        self.mic_monitor.start()

    def restart_microphone(self):
        if self.mic_monitor:
            self.mic_monitor.stop()
        self.start_microphone()
        self.set_unsaved(True)

    # ---------------- Preset list ----------------
    def load_presets(self):
        self.preset_list.clear()
        os.makedirs(PRISSETS_DIR, exist_ok=True)
        for name in sorted(os.listdir(PRISSETS_DIR)):
            if os.path.isdir(os.path.join(PRISSETS_DIR, name)):
                self.preset_list.addItem(name)

    # ---------------- Config form ----------------
    def load_config(self):
        for i in reversed(range(self.config_form.count())):
            self.config_form.removeRow(i)

        self.config_fields = {}
        self.set_unsaved(False)

        item = self.preset_list.currentItem()
        if not item:
            return

        path = os.path.join(PRISSETS_DIR, item.text(), "Config.json")
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Ошибка", "Config.json не найден")
            return

        with open(path, "r", encoding="utf-8") as f:
            self.config_data = json.load(f)

        # Microphone section
        if "Microphone" in self.config_data:
            self.add_microphone_widgets()
            idx = self.config_data["Microphone"].get("DeviceIndex")
            if idx is not None:
                i = self.mic_combo.findData(idx)
                if i != -1:
                    self.mic_combo.blockSignals(True)
                    self.mic_combo.setCurrentIndex(i)
                    self.mic_combo.blockSignals(False)

        self._create_form(self.config_data)

    def _create_form(self, data):
        for category in CATEGORY_ORDER:
            if category in data:
                cat_label = QLabel(category)
                cat_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 15px; color: #555;")
                self.config_form.addRow(cat_label)
                self._add_fields(data[category], category)

    def _add_fields(self, subdata, parent):
        for key, value in subdata.items():
            full = f"{parent}.{key}"
            if isinstance(value, dict):
                self._add_fields(value, full)
                continue

            display = -value if full.endswith("JumpAmplitude") and isinstance(value, (int, float)) else value

            if isinstance(value, bool):
                w = QCheckBox()
                w.setChecked(display)
                w.stateChanged.connect(lambda _, f=full: self.set_unsaved(True))
            elif isinstance(value, int):
                w = QSpinBox()
                w.setRange(-999999, 999999)
                w.setValue(display)
                w.valueChanged.connect(lambda _, f=full: self.set_unsaved(True))
            elif isinstance(value, float):
                w = QDoubleSpinBox()
                w.setRange(-999999.0, 999999.0)
                w.setDecimals(2)
                w.setSingleStep(0.05 if "Smoothing" in full else 10.0)
                w.setValue(display)
                w.valueChanged.connect(lambda _, f=full: self.set_unsaved(True))
            elif isinstance(value, list):
                w = QLineEdit(", ".join(map(str, value)))
                w.textChanged.connect(lambda _, f=full: self.set_unsaved(True))
            else:
                w = QLineEdit(str(display))
                w.textChanged.connect(lambda _, f=full: self.set_unsaved(True))

            self.config_form.addRow(key, w)
            self.config_fields[full] = w

            # Tooltips для лучшей понятности
            if full == "Microphone.MaxVolume":
                w.setToolTip("Максимальный ожидаемый уровень громкости.\nПодберите по пиковому значению в индикаторе Mic Level (рекомендуется 2000–5000).")
            elif full == "Microphone.BackgroundNoise":
                w.setToolTip("Уровень фонового шума, который вычитается.\n20–100 в зависимости от шумности помещения.")
            elif full == "LipSync.Smoothing":
                w.setToolTip("Сглаживание громкости для плавного открытия рта.\n0.0 — без сглаживания (дерганье), 1.0 — очень плавно.\nРекомендуется 0.6–0.8.")
            elif full == "LipSync.HysteresisHigh":
                w.setToolTip("Порог начала детекции речи.\nВыше этого значения аватар считает, что вы начали говорить.")
            elif full == "LipSync.HysteresisLow":
                w.setToolTip("Порог удержания речи (должен быть ниже High).\nПомогает не прерывать рот на коротких паузах между словами.")
            elif full == "EmotionBlink.Threshold":
                w.setToolTip("Порог резкого всплеска громкости для эмоционального моргания.\nВыше значение — реже срабатывает (2500–4000 для спокойной речи).")
            elif full == "EmotionBlink.Enabled":
                w.setToolTip("Включить эмоциональное моргание на громкие всплески.")
            elif full == "Mouth.FrameInterval":
                w.setToolTip("Интервал обновления кадра рта в секундах.\nМеньше — быстрее реакция, но может дёргаться (0.03–0.1).")
            elif full == "Mouth.CloseDelay":
                w.setToolTip("Задержка закрытия рта после окончания речи (в секундах).")
            elif full == "Movement.JumpAmplitude":
                w.setToolTip("Амплитуда прыжков при громкой речи (положительное значение).")

            elif full == "Movement.DynamicSquashEnabled":
                w.setToolTip("Р›РµРіРєРѕ РїСЂРёРїР»СЋС‰РёРІР°РµС‚ Р°РІР°С‚Р°СЂ РІРѕ РІСЂРµРјСЏ СЂРµС‡Рё, С‡С‚РѕР±С‹ РѕРЅ РІС‹РіР»СЏРґРµР» Р¶РёРІРµРµ.")
            elif full == "Movement.DynamicSquashAmount":
                w.setToolTip("РЎРёР»Р° РґРёРЅР°РјРёС‡РµСЃРєРѕРіРѕ РїСЂРёРїР»СЋС‰РёРІР°РЅРёСЏ РІРѕ РІСЂРµРјСЏ СЂРµС‡Рё. РћР±С‹С‡РЅРѕ С…РѕСЂРѕС€Рѕ СЂР°Р±РѕС‚Р°РµС‚ РІ РґРёР°РїР°Р·РѕРЅРµ 0.04-0.12.")

    # ---------------- Save config ----------------
    def save_config(self):
        def set_value(d, path, val):
            keys = path.split(".")
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            if keys[-1] == "JumpAmplitude":
                val = -val
            d[keys[-1]] = val

        for full_key, widget in self.config_fields.items():
            if isinstance(widget, QCheckBox):
                v = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                v = widget.value()
            else:
                t = widget.text().strip()
                if not t:
                    v = []
                else:
                    parts = [p.strip() for p in t.split(',')]
                    try:
                        v = [float(p) for p in parts]
                    except ValueError:
                        v = parts
            set_value(self.config_data, full_key, v)

        if hasattr(self, "mic_combo"):
            self.config_data.setdefault("Microphone", {})
            self.config_data["Microphone"]["DeviceIndex"] = self.mic_combo.currentData()

        item = self.preset_list.currentItem()
        if item:
            path = os.path.join(PRISSETS_DIR, item.text(), "Config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)

        self.set_unsaved(False)

    # ---------------- Preset management ----------------
    def create_preset(self):
        name, ok = QInputDialog.getText(self, "Создать пресет", "Введите имя пресета:")
        if not ok or not name.strip():
            return
        name = name.strip()
        path = os.path.join(PRISSETS_DIR, name)
        if os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", "Пресет с таким именем уже существует!")
            return

        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "Sprites"), exist_ok=True)

        default_config = {
            "Window": {
                "Size": [1080],
                "Scale": 1.0,
                "Reflect": False,
                "UseChromaKey": True,
                "ChromaKeyColor": [0, 255, 0],
                "AlwaysOnTop": False
            },
            "Microphone": {
                "MaxVolume": 3000,  # более реалистичный дефолт
                "BackgroundNoise": 50
            },
            "LipSync": {
                "Smoothing": 0.7,
                "HysteresisHigh": 120.0,
                "HysteresisLow": 50.0
            },
            "Blink": {
                "Interval": [4, 8],
                "Durations": [0.2]
            },
            "EmotionBlink": {
                "Enabled": True,
                "Threshold": 2500,  # выше, чтобы не срабатывало на спокойной речи
                "Durations": [0.75]
            },
            "Movement": {
                "JumpAmplitude": -14,
                "DynamicSquashEnabled": True,
                "DynamicSquashAmount": 0.08,
                "VerticalSway": [0, 0],
                "HorizontalSway": [0, 0]
            },
            "Mouth": {
                "FrameInterval": 0.05,
                "UseCloseDelay": True,
                "CloseDelay": 0.35
            }
        }

        with open(os.path.join(path, "Config.json"), "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)

        self.load_presets()
        items = self.preset_list.findItems(name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])
            self.load_config()

    # Остальные методы (copy_preset, delete_preset, rename_preset, open_folder, run_avatar, stop_avatar) остаются без изменений
    def copy_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        base_name = item.text() + "_Copy"
        name = base_name
        i = 1
        while os.path.exists(os.path.join(PRISSETS_DIR, name)):
            name = f"{base_name}_{i}"
            i += 1

        shutil.copytree(os.path.join(PRISSETS_DIR, item.text()), os.path.join(PRISSETS_DIR, name))
        self.load_presets()

        items = self.preset_list.findItems(name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])
            self.load_config()

    def delete_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        reply = QMessageBox.question(
            self, "Удалить", f"Удалить пресет {item.text()}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            shutil.rmtree(os.path.join(PRISSETS_DIR, item.text()))
            self.load_presets()

    def rename_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        old_name = item.text()
        new_name, ok = QInputDialog.getText(
            self, "Переименовать пресет", "Новое имя:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        old_path = os.path.join(PRISSETS_DIR, old_name)
        new_path = os.path.join(PRISSETS_DIR, new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Ошибка", "Пресет с таким именем уже существует!")
            return

        os.rename(old_path, new_path)
        self.load_presets()

        items = self.preset_list.findItems(new_name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])
            self.load_config()

    def open_folder(self):
        item = self.preset_list.currentItem()
        if not item:
            return
        path = os.path.abspath(os.path.join(PRISSETS_DIR, item.text()))
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def run_avatar(self):
        self.save_config()
        item = self.preset_list.currentItem()
        if not item:
            return
        if self.process is not None:
            QMessageBox.warning(self, "Ошибка", "Аватар уже запущен")
            return

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            [sys.executable, "avatar.py", item.text()],
            creationflags=creationflags
        )

    def stop_avatar(self):
        if self.process:
            self.process.terminate()
            self.process = None


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            from PyQt5.QtWinExtras import QtWin
            QtWin.setCurrentProcessExplicitAppUserModelID("com.mycompany.PNG2B.v2_2")
        except ImportError:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.mycompany.PNG2B.v2_2")

    app = QApplication(sys.argv)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = PresetManager()
    window.show()
    sys.exit(app.exec_())
