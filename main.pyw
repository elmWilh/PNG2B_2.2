import json
import os
import shutil
import subprocess
import sys
import threading

import numpy as np
import pyaudio
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from app_meta import APP_PRESET_MANAGER_TITLE, APP_USER_MODEL_ID

PRISSETS_DIR = "Prissets"
ICON_PATH = "PNG2B.ico"
CATEGORY_ORDER = ["Window", "Microphone", "LipSync", "Blink", "EmotionBlink", "Movement", "Mouth"]

CATEGORY_META = {
    "Window": ("Отображение аватара", "Размер, отражение, прозрачность и поведение аватара."),
    "Microphone": ("Микрофон", "Выбор устройства и базовая чувствительность."),
    "LipSync": ("Липсинк", "Насколько плавно и уверенно рот реагирует на голос."),
    "Blink": ("Обычное моргание", "Интервал и длительность обычного моргания."),
    "EmotionBlink": ("Эмоциональное моргание", "Реакция на резкие всплески громкости."),
    "Movement": ("Движение", "Подпрыгивание, покачивание и squash/stretch."),
    "Mouth": ("Рот", "Скорость смены кадров и мягкое закрытие рта."),
}

FIELD_META = {
    "Window.Size": ("Размер аватара", ""),
    "Window.Scale": ("Масштаб спрайтов", ""),
    "Window.Reflect": ("Отразить по горизонтали", ""),
    "Window.UseChromaKey": ("Использовать хромакей", ""),
    "Window.ChromaKeyColor": ("Цвет хромакея", "RGB-цвет, который будет считаться прозрачным."),
    "Window.AlwaysOnTop": ("Поверх всех окон", ""),
    "Microphone.DeviceIndex": ("Устройство ввода", ""),
    "Microphone.MaxVolume": ("Максимальная громкость", "Примерный потолок громкости. Чем он выше, тем спокойнее реагирует рот."),
    "Microphone.BackgroundNoise": ("Фоновый шум", "Постоянный шум, который нужно вычитать из сигнала."),
    "LipSync.Smoothing": ("Сглаживание", "Чем выше значение, тем плавнее рот, но тем медленнее реакция."),
    "LipSync.HysteresisHigh": ("Порог начала речи", "Выше этого уровня аватар считает, что вы начали говорить."),
    "LipSync.HysteresisLow": ("Порог удержания речи", "Ниже этого уровня речь считается законченной. Должен быть меньше верхнего порога."),
    "Blink.Interval": ("Интервал моргания", "Минимальная и максимальная пауза между морганиями, в секундах."),
    "Blink.Durations": ("Длительность кадров", ""),
    "EmotionBlink.Enabled": ("Включить", ""),
    "EmotionBlink.Threshold": ("Порог всплеска", "Насколько сильным должен быть резкий скачок громкости."),
    "EmotionBlink.Durations": ("Длительность кадров", ""),
    "Movement.Mode": ("Режим движения", "Squash — сжатие при речи, Bounce — подёргивание вверх-вниз, Static — без движения."),
    "Movement.JumpAmplitude": ("Сила подпрыгивания", ""),
    "Movement.DynamicSquashEnabled": ("Включить squash/stretch", ""),
    "Movement.DynamicSquashAmount": ("Сила squash/stretch", "Насколько заметно аватар будет сжиматься и растягиваться."),
    "Movement.VerticalSway": ("Вертикальное покачивание", "Амплитуда и частота медленного движения вверх-вниз."),
    "Movement.HorizontalSway": ("Горизонтальное покачивание", "Амплитуда и частота медленного движения влево-вправо."),
    "Mouth.FrameInterval": ("Интервал кадров рта", ""),
    "Mouth.UseCloseDelay": ("Плавное закрытие", ""),
    "Mouth.CloseDelay": ("Задержка закрытия", "Сколько секунд ждать перед полным закрытием рта."),
}


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

    mojibake_markers = (
        "Р",
        "С",
        "Ð",
        "Ñ",
        "Ã",
        "�",
    )
    if not any(marker in text for marker in mojibake_markers):
        return text

    if "Р" in text or "С" in text:
        try:
            fixed = text.encode("cp1251").decode("utf-8")
            fixed_lower_cyrillic = sum(1 for ch in fixed if "\u0430" <= ch <= "\u044f" or ch in ("ё",))
            text_lower_cyrillic = sum(1 for ch in text if "\u0430" <= ch <= "\u044f" or ch in ("ё",))
            if fixed_lower_cyrillic > text_lower_cyrillic:
                return fixed
        except Exception:
            pass

    candidates = [text]
    for source_encoding, target_encoding in (
        ("latin1", "utf-8"),
        ("cp1251", "utf-8"),
        ("cp866", "utf-8"),
        ("utf-8", "cp1251"),
        ("utf-8", "cp866"),
    ):
        try:
            candidates.append(text.encode(source_encoding).decode(target_encoding))
        except Exception:
            pass

    def score(value):
        suspicious = sum(value.count(ch) for ch in mojibake_markers)
        cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04FF")
        lower_cyrillic = sum(1 for ch in value if "\u0430" <= ch <= "\u044f" or ch in ("ё",))
        upper_cyrillic = sum(1 for ch in value if "\u0410" <= ch <= "\u042f" or ch in ("Ё",))
        latin = sum(1 for ch in value if "A" <= ch <= "z")
        replacement = value.count("\ufffd")
        mojibake_pairs = sum(
            1
            for first, second in zip(value, value[1:])
            if first in ("Р", "С", "Ð", "Ñ", "Ã")
            and second not in (" ", "(", ")", "-", "_")
        )
        return (
            lower_cyrillic * 5 + cyrillic * 2 + latin - upper_cyrillic * 2 - suspicious * 4 - mojibake_pairs * 6 - replacement * 4,
            -mojibake_pairs,
            -suspicious,
            lower_cyrillic,
            -replacement,
            -len(value),
        )

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
                frames_per_buffer=1024,
            )
            while self.running:
                data = stream.read(1024, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.int16)
                try:
                    level = int(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                    if np.isnan(level):
                        level = 0
                except Exception:
                    level = 0
                self.level_changed.emit(level)
            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()


class NumericTupleEditor(QWidget):
    value_changed = pyqtSignal()

    def __init__(self, labels, values, minimum=-999999.0, maximum=999999.0, decimals=2, step=1.0):
        super().__init__()
        self.setObjectName("TupleEditor")
        self._spinboxes = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for index, raw_value in enumerate(values):
            wrap = QVBoxLayout()
            wrap.setContentsMargins(0, 0, 0, 0)
            wrap.setSpacing(2)

            caption = QLabel(labels[index] if index < len(labels) else f"Значение {index + 1}")
            caption.setObjectName("MiniLabel")

            spin = NoWheelDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
            spin.setValue(float(raw_value))
            spin.valueChanged.connect(self.value_changed.emit)

            wrap.addWidget(caption)
            wrap.addWidget(spin)
            layout.addLayout(wrap)
            self._spinboxes.append(spin)

        layout.addStretch(1)

    def values(self):
        return [spin.value() for spin in self._spinboxes]


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class PresetManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_data = {}
        self.config_fields = {}
        self.mic_monitor = None
        self.process = None
        self.unsaved = False
        self.current_preset_name = None
        self._changing_selection = False

        self.setWindowTitle(APP_PRESET_MANAGER_TITLE)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1220, 760)
        self._apply_styles()
        self._build_ui()
        self.avatar_status_timer = QTimer(self)
        self.avatar_status_timer.timeout.connect(self.refresh_avatar_status)
        self.avatar_status_timer.start(700)
        self.load_presets()
        self.set_unsaved(False)
        self.refresh_avatar_status()

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #f4f7fb;
                color: #1f2937;
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QListWidget, QLineEdit, QComboBox, QDoubleSpinBox, QProgressBar, QGroupBox {
                background: white;
                border: 1px solid #d7deea;
                border-radius: 10px;
            }
            QListWidget {
                padding: 6px;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-radius: 8px;
                margin: 2px 0;
            }
            QListWidget::item:selected {
                background: #dceeff;
                color: #0f172a;
            }
            QPushButton {
                background: white;
                border: 1px solid #cfd8e6;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #eef4fb;
            }
            QPushButton#PrimaryButton {
                background: #0f766e;
                color: white;
                border-color: #0f766e;
            }
            QPushButton#PrimaryButton:hover {
                background: #0d6b64;
            }
            QGroupBox {
                margin-top: 14px;
                padding: 18px 18px 16px 18px;
                font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QLabel#Title {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#Subtitle {
                color: #5b6472;
                font-size: 12px;
            }
            QLabel#BadgeSaved {
                background: #dcfce7;
                color: #166534;
                border-radius: 999px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QLabel#BadgeUnsaved {
                background: #fee2e2;
                color: #b91c1c;
                border-radius: 999px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QLabel#BadgeRunning {
                background: #dcfce7;
                color: #166534;
                border-radius: 999px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QLabel#BadgeStopped {
                background: #e5e7eb;
                color: #374151;
                border-radius: 999px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QLabel#SectionHint {
                color: #667085;
                padding-bottom: 4px;
            }
            QLabel#FieldTitle {
                font-weight: 700;
                color: #111827;
            }
            QLabel#FieldHint {
                color: #6b7280;
                font-size: 12px;
            }
            QLabel#MiniLabel {
                color: #64748b;
                font-size: 11px;
            }
            QWidget#FieldRow, QWidget#TupleEditor, QWidget#MicLevelWidget {
                background: transparent;
                border: none;
            }
            QProgressBar {
                height: 18px;
                text-align: center;
            }
            QProgressBar::chunk {
                border-radius: 8px;
                background: #14b8a6;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 12px;
                margin: 6px 0 6px 0;
            }
            QScrollBar::handle:vertical {
                background: #b8c4d6;
                min-height: 40px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 12px;
                margin: 0 6px 0 6px;
            }
            QScrollBar::handle:horizontal {
                background: #b8c4d6;
                min-width: 40px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            """
        )

    def _build_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        splitter = QSplitter(Qt.Horizontal)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(12)

        left_header = QLabel("Пресеты")
        left_header.setObjectName("Title")
        self.preset_list = QListWidget()
        self.preset_list.currentItemChanged.connect(self.on_preset_selection_changed)
        self.preset_list.itemDoubleClicked.connect(self.rename_preset)

        self.btn_create = QPushButton("Новый")
        self.btn_copy = QPushButton("Дубликат")
        self.btn_delete = QPushButton("Удалить")
        self.btn_open = QPushButton("Открыть папку")
        self.btn_run = QPushButton("Запустить")
        self.btn_stop = QPushButton("Остановить")
        self.btn_save = QPushButton("Сохранить изменения")
        self.btn_reset_defaults = QPushButton("Вернуть стандартные")
        self.btn_save.setObjectName("PrimaryButton")

        self.btn_create.clicked.connect(self.create_preset)
        self.btn_copy.clicked.connect(self.copy_preset)
        self.btn_delete.clicked.connect(self.delete_preset)
        self.btn_open.clicked.connect(self.open_folder)
        self.btn_run.clicked.connect(self.run_avatar)
        self.btn_stop.clicked.connect(self.stop_avatar)
        self.btn_save.clicked.connect(self.save_config)
        self.btn_reset_defaults.clicked.connect(self.reset_to_defaults)

        top_buttons = QHBoxLayout()
        top_buttons.setSpacing(8)
        top_buttons.addWidget(self.btn_create)
        top_buttons.addWidget(self.btn_copy)
        top_buttons.addWidget(self.btn_delete)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.setSpacing(8)
        bottom_buttons.addWidget(self.btn_open)
        bottom_buttons.addWidget(self.btn_run)
        bottom_buttons.addWidget(self.btn_stop)

        sidebar_layout.addWidget(left_header)
        sidebar_layout.addWidget(self.preset_list, 1)
        sidebar_layout.addLayout(top_buttons)
        sidebar_layout.addLayout(bottom_buttons)
        sidebar_layout.addWidget(self.btn_reset_defaults)
        sidebar_layout.addWidget(self.btn_save)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_column = QVBoxLayout()
        title_column.setSpacing(4)
        self.current_preset_label = QLabel("")
        self.current_preset_label.setObjectName("Title")
        self.current_path_label = QLabel("")
        self.current_path_label.setObjectName("Subtitle")
        title_column.addWidget(self.current_preset_label)
        title_column.addWidget(self.current_path_label)

        self.unsaved_label = QLabel("Сохранено")
        self.unsaved_label.setObjectName("BadgeSaved")
        self.avatar_status_label = QLabel("Аватар остановлен")
        self.avatar_status_label.setObjectName("BadgeStopped")

        header_layout.addLayout(title_column, 1)
        header_layout.addWidget(self.avatar_status_label, 0, Qt.AlignTop)
        header_layout.addWidget(self.unsaved_label, 0, Qt.AlignTop)

        self.sections_container = QWidget()
        self.sections_layout = QVBoxLayout(self.sections_container)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(10)
        self.sections_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.sections_container)

        right_layout.addWidget(header_widget)
        right_layout.addWidget(scroll, 1)

        splitter.addWidget(sidebar)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 870])

        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(splitter)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _field_meta(self, full_key, fallback_name):
        return FIELD_META.get(full_key, (fallback_name, ""))

    def _normalize_config_data(self):
        window = self.config_data.setdefault("Window", {})
        size = window.get("Size", [1080, 1080])
        if not isinstance(size, (list, tuple)):
            size = [size]
        if len(size) == 1:
            size = [size[0], size[0]]
        elif len(size) < 2:
            size = [1080, 1080]
        window["Size"] = [max(1, int(size[0])), max(1, int(size[1]))]

        movement = self.config_data.setdefault("Movement", {})
        mode = movement.get("Mode")
        if not mode:
            mode = "Squash" if movement.get("DynamicSquashEnabled", True) else "Bounce"
        mode = str(mode).strip().capitalize()
        if mode not in {"Squash", "Bounce", "Static"}:
            mode = "Squash"
        movement["Mode"] = mode
        movement["DynamicSquashEnabled"] = mode == "Squash"

    def _default_config_template(self):
        return {
            "Window": {
                "Size": [1080, 1080],
                "Scale": 1.0,
                "Reflect": False,
                "UseChromaKey": True,
                "ChromaKeyColor": [0, 255, 0],
                "AlwaysOnTop": False,
            },
            "Microphone": {
                "MaxVolume": 3000,
                "BackgroundNoise": 50,
                "DeviceIndex": None,
            },
            "LipSync": {
                "Smoothing": 0.7,
                "HysteresisHigh": 120.0,
                "HysteresisLow": 50.0,
            },
            "Blink": {
                "Interval": [4.0, 8.0],
                "Durations": [0.2],
            },
            "EmotionBlink": {
                "Enabled": True,
                "Threshold": 2500,
                "Durations": [0.75],
            },
            "Movement": {
                "Mode": "Squash",
                "JumpAmplitude": -14,
                "DynamicSquashAmount": 0.08,
                "VerticalSway": [0.0, 0.0],
                "HorizontalSway": [0.0, 0.0],
            },
            "Mouth": {
                "FrameInterval": 0.05,
                "UseCloseDelay": True,
                "CloseDelay": 0.35,
            },
        }

    def _mark_unsaved(self):
        if not self._changing_selection:
            self.set_unsaved(True)

    def _register_widget(self, full_key, widget, value_type, original_value):
        self.config_fields[full_key] = {
            "widget": widget,
            "type": value_type,
            "original": original_value,
        }

        if isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self._mark_unsaved)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self._mark_unsaved)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self._mark_unsaved)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self._mark_unsaved)
        elif isinstance(widget, NumericTupleEditor):
            widget.value_changed.connect(self._mark_unsaved)

    def _build_field_row(self, field_title, field_hint, editor):
        container = QWidget()
        container.setObjectName("FieldRow")
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 2, 0, 8)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(4)

        title = QLabel(field_title)
        title.setObjectName("FieldTitle")
        title.setWordWrap(True)

        hint = QLabel(field_hint)
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        hint.setVisible(bool(field_hint))

        layout.addWidget(title, 0, 0)
        layout.addWidget(hint, 1, 0)
        layout.addWidget(editor, 0, 1, 2, 1)
        layout.setColumnStretch(0, 4)
        layout.setColumnStretch(1, 3)
        return container

    def _create_numeric_spin(self, value, step=1.0, minimum=-999999.0, maximum=999999.0, decimals=2):
        spin = NoWheelDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(float(value))
        spin.setMinimumWidth(180)
        return spin

    def _create_editor_for_value(self, full_key, value):
        if full_key == "Movement.Mode":
            editor = NoWheelComboBox()
            editor.addItem("Squash", "Squash")
            editor.addItem("Bounce", "Bounce")
            editor.addItem("Static", "Static")
            selected_value = str(value).strip().capitalize()
            position = editor.findData(selected_value)
            if position == -1:
                position = 0
            editor.setCurrentIndex(position)
            self._register_widget(full_key, editor, "choice", selected_value)
            return editor

        if full_key == "Movement.JumpAmplitude":
            value = abs(float(value))
            editor = self._create_numeric_spin(value, step=1.0, minimum=0.0, maximum=999999.0, decimals=0)
            self._register_widget(full_key, editor, "jump", value)
            return editor

        if full_key == "Window.Size" and isinstance(value, list) and len(value) >= 2:
            editor = NumericTupleEditor(["Ширина", "Высота"], value[:2], minimum=1.0, maximum=999999.0, decimals=0, step=1.0)
            self._register_widget(full_key, editor, "int_tuple", value[:2])
            return editor

        if full_key == "Window.ChromaKeyColor" and isinstance(value, list) and len(value) == 3:
            editor = NumericTupleEditor(["R", "G", "B"], value, minimum=0.0, maximum=255.0, decimals=0, step=1.0)
            self._register_widget(full_key, editor, "int_tuple", value)
            return editor

        if isinstance(value, bool):
            editor = QCheckBox("Включено")
            editor.setChecked(value)
            self._register_widget(full_key, editor, "bool", value)
            return editor

        if isinstance(value, (int, float)):
            decimals = 0 if isinstance(value, int) and full_key not in {"LipSync.Smoothing", "Window.Scale", "Mouth.FrameInterval", "Mouth.CloseDelay", "Movement.DynamicSquashAmount"} else 3
            step = 0.05 if full_key in {"LipSync.Smoothing", "Window.Scale", "Movement.DynamicSquashAmount"} else 1.0
            if full_key in {"Mouth.FrameInterval", "Mouth.CloseDelay"}:
                step = 0.01
            editor = self._create_numeric_spin(value, step=step, decimals=decimals)
            self._register_widget(full_key, editor, "number", value)
            return editor

        if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
            labels = ["От", "До"] if full_key == "Blink.Interval" else ["Амплитуда", "Частота"]
            editor = NumericTupleEditor(labels, value, decimals=3, step=0.1)
            self._register_widget(full_key, editor, "float_tuple", value)
            return editor

        if isinstance(value, list):
            editor = QLineEdit(", ".join(map(str, value)))
            editor.setPlaceholderText("Введите значения через запятую")
            self._register_widget(full_key, editor, "list_text", value)
            return editor

        editor = QLineEdit(str(value))
        self._register_widget(full_key, editor, "text", value)
        return editor

    def _add_microphone_widgets(self, layout, mic_data):
        row_title, row_hint = self._field_meta("Microphone.DeviceIndex", "Устройство ввода")

        self.mic_combo = NoWheelComboBox()
        self.mics = self.list_microphones()
        for idx, name in self.mics:
            self.mic_combo.addItem(name, idx)

        saved_idx = mic_data.get("DeviceIndex")
        if saved_idx is not None:
            pos = self.mic_combo.findData(saved_idx)
            if pos != -1:
                self.mic_combo.setCurrentIndex(pos)

        self.mic_combo.currentIndexChanged.connect(self.restart_microphone)
        self._register_widget("Microphone.DeviceIndex", self.mic_combo, "mic_device", saved_idx)
        layout.addWidget(self._build_field_row(row_title, row_hint, self.mic_combo))

        mic_level_widget = QWidget()
        mic_level_widget.setObjectName("MicLevelWidget")
        mic_level_layout = QVBoxLayout(mic_level_widget)
        mic_level_layout.setContentsMargins(0, 0, 0, 0)
        mic_level_layout.setSpacing(6)

        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 5000)
        self.mic_level.setFormat("%v")

        mic_caption = QLabel("Живой уровень микрофона. Смотрите на пики и под них подбирайте MaxVolume.")
        mic_caption.setObjectName("FieldHint")
        mic_caption.setWordWrap(True)

        mic_level_layout.addWidget(self.mic_level)
        mic_level_layout.addWidget(mic_caption)
        layout.addWidget(self._build_field_row("Уровень сигнала", "Помогает понять, как аватар видит ваш голос прямо сейчас.", mic_level_widget))

        self.start_microphone()

    def _populate_sections(self):
        self._clear_layout(self.sections_layout)
        self.config_fields = {}

        if not self.config_data:
            self.sections_layout.addStretch(1)
            return

        for category in CATEGORY_ORDER:
            if category not in self.config_data:
                continue

            title, description = CATEGORY_META.get(category, (category, ""))
            box = QGroupBox(title)
            section_layout = QVBoxLayout(box)
            section_layout.setSpacing(8)

            if description:
                desc = QLabel(description)
                desc.setWordWrap(True)
                desc.setObjectName("SectionHint")
                section_layout.addWidget(desc)

            if category == "Microphone":
                self._add_microphone_widgets(section_layout, self.config_data[category])

            for key, value in self.config_data[category].items():
                full_key = f"{category}.{key}"
                if full_key in {"Microphone.DeviceIndex", "Movement.DynamicSquashEnabled"}:
                    continue

                field_title, field_hint = self._field_meta(full_key, key)
                editor = self._create_editor_for_value(full_key, value)
                section_layout.addWidget(self._build_field_row(field_title, field_hint, editor))

            section_layout.addSpacerItem(QSpacerItem(0, 4, QSizePolicy.Minimum, QSizePolicy.Expanding))
            self.sections_layout.addWidget(box)

        self.sections_layout.addStretch(1)

    def _prompt_unsaved_changes(self):
        if not self.unsaved:
            return "discard"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Несохранённые изменения")
        box.setText("В текущем пресете есть несохранённые изменения.")
        box.setInformativeText("Сохранить их перед переключением или закрытием?")
        save_button = box.addButton("Сохранить", QMessageBox.AcceptRole)
        discard_button = box.addButton("Не сохранять", QMessageBox.DestructiveRole)
        cancel_button = box.addButton("Отмена", QMessageBox.RejectRole)
        box.setDefaultButton(save_button)
        box.exec_()

        clicked = box.clickedButton()
        if clicked == save_button:
            return "save"
        if clicked == discard_button:
            return "discard"
        return "cancel"

    def _read_widget_value(self, field_info):
        widget = field_info["widget"]
        kind = field_info["type"]
        original = field_info["original"]

        if kind == "bool":
            return widget.isChecked()
        if kind == "number":
            value = widget.value()
            return int(round(value)) if isinstance(original, int) else float(value)
        if kind == "jump":
            return -abs(int(round(widget.value())))
        if kind == "int_tuple":
            return [int(round(v)) for v in widget.values()]
        if kind == "float_tuple":
            values = widget.values()
            if all(isinstance(v, int) for v in original):
                return [int(round(v)) for v in values]
            return [float(v) for v in values]
        if kind == "list_text":
            raw = widget.text().strip()
            if not raw:
                return []
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            if original and all(isinstance(item, (int, float)) for item in original):
                parsed = [float(part) for part in parts]
                if all(isinstance(item, int) for item in original):
                    return [int(round(value)) for value in parsed]
                return parsed
            return parts
        if kind == "text":
            return widget.text()
        if kind == "choice":
            return widget.currentData()
        if kind == "mic_device":
            return widget.currentData()
        return None

    def _set_nested_value(self, data, path, value):
        keys = path.split(".")
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        data[keys[-1]] = value

    def closeEvent(self, event):
        action = self._prompt_unsaved_changes()
        if action == "cancel":
            event.ignore()
            return
        if action == "save":
            self.save_config()

        if self.mic_monitor:
            self.mic_monitor.stop()
            self.mic_monitor = None
        if self.process:
            self.process.terminate()
            self.process = None
        self.refresh_avatar_status()
        event.accept()

    def set_unsaved(self, value=True):
        self.unsaved = value
        if value:
            self.unsaved_label.setText("Есть несохранённые")
            self.unsaved_label.setObjectName("BadgeUnsaved")
        else:
            self.unsaved_label.setText("Сохранено")
            self.unsaved_label.setObjectName("BadgeSaved")
        self.unsaved_label.style().unpolish(self.unsaved_label)
        self.unsaved_label.style().polish(self.unsaved_label)

    def refresh_avatar_status(self):
        running = self.process is not None and self.process.poll() is None
        if not running and self.process is not None:
            self.process = None

        if running:
            self.avatar_status_label.setText("Аватар запущен")
            self.avatar_status_label.setObjectName("BadgeRunning")
        else:
            self.avatar_status_label.setText("Аватар остановлен")
            self.avatar_status_label.setObjectName("BadgeStopped")

        self.avatar_status_label.style().unpolish(self.avatar_status_label)
        self.avatar_status_label.style().polish(self.avatar_status_label)

    def list_microphones(self):
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                devices.append((i, repair_text(info.get("name", f"Input Device {i}"))))
        p.terminate()
        return devices

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
        self._mark_unsaved()

    def load_presets(self):
        self.preset_list.clear()
        os.makedirs(PRISSETS_DIR, exist_ok=True)
        for name in sorted(os.listdir(PRISSETS_DIR)):
            if os.path.isdir(os.path.join(PRISSETS_DIR, name)):
                self.preset_list.addItem(name)

        if self.preset_list.count() and self.current_preset_name:
            matches = self.preset_list.findItems(self.current_preset_name, Qt.MatchExactly)
            if matches:
                self._changing_selection = True
                self.preset_list.setCurrentItem(matches[0])
                self._changing_selection = False

    def on_preset_selection_changed(self, current, previous):
        if self._changing_selection:
            return

        if previous is not None and self.unsaved and current != previous:
            action = self._prompt_unsaved_changes()
            if action == "cancel":
                self._changing_selection = True
                self.preset_list.setCurrentItem(previous)
                self._changing_selection = False
                return
            if action == "save":
                self.save_config()

        self.load_config(current)

    def load_config(self, item=None):
        if item is None:
            item = self.preset_list.currentItem()

        self.config_data = {}
        self.current_preset_name = item.text() if item else None

        if self.mic_monitor:
            self.mic_monitor.stop()
            self.mic_monitor = None

        if not item:
            self.current_preset_label.setText("")
            self.current_path_label.setText("")
            self._populate_sections()
            self.set_unsaved(False)
            return

        preset_name = item.text()
        path = os.path.join(PRISSETS_DIR, preset_name, "Config.json")
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Ошибка", "Config.json не найден")
            return

        with open(path, "r", encoding="utf-8") as file:
            self.config_data = json.load(file)

        self._normalize_config_data()
        self.current_preset_label.setText(preset_name)
        self.current_path_label.setText(os.path.abspath(os.path.join(PRISSETS_DIR, preset_name)))
        self._populate_sections()
        self.set_unsaved(False)

    def save_config(self):
        item = self.preset_list.currentItem()
        if not item or not self.config_data:
            return

        for full_key, field_info in self.config_fields.items():
            try:
                value = self._read_widget_value(field_info)
            except ValueError:
                title, _ = self._field_meta(full_key, full_key.split(".")[-1])
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить поле: {title}")
                return
            self._set_nested_value(self.config_data, full_key, value)

        self._normalize_config_data()

        path = os.path.join(PRISSETS_DIR, item.text(), "Config.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(self.config_data, file, indent=2, ensure_ascii=False)

        self.set_unsaved(False)

    def create_preset(self):
        name, ok = QInputDialog.getText(self, "Создать пресет", "Введите имя нового пресета:")
        if not ok or not name.strip():
            return

        name = name.strip()
        path = os.path.join(PRISSETS_DIR, name)
        if os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", "Пресет с таким именем уже существует.")
            return

        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "Sprites"), exist_ok=True)

        default_config = self._default_config_template()

        with open(os.path.join(path, "Config.json"), "w", encoding="utf-8") as file:
            json.dump(default_config, file, indent=2, ensure_ascii=False)

        self.load_presets()
        items = self.preset_list.findItems(name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])

    def copy_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        base_name = f"{item.text()}_Copy"
        name = base_name
        index = 1
        while os.path.exists(os.path.join(PRISSETS_DIR, name)):
            name = f"{base_name}_{index}"
            index += 1

        shutil.copytree(os.path.join(PRISSETS_DIR, item.text()), os.path.join(PRISSETS_DIR, name))
        self.load_presets()
        items = self.preset_list.findItems(name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])

    def delete_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        reply = QMessageBox.question(
            self,
            "Удалить пресет",
            f"Удалить пресет {item.text()}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            shutil.rmtree(os.path.join(PRISSETS_DIR, item.text()))
            self.current_preset_name = None
            self.load_presets()
            self.load_config(None)

    def rename_preset(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        old_name = item.text()
        new_name, ok = QInputDialog.getText(self, "Переименовать пресет", "Новое имя:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        old_path = os.path.join(PRISSETS_DIR, old_name)
        new_path = os.path.join(PRISSETS_DIR, new_name)

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Ошибка", "Пресет с таким именем уже существует.")
            return

        os.rename(old_path, new_path)
        self.current_preset_name = new_name
        self.load_presets()
        items = self.preset_list.findItems(new_name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])

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
            QMessageBox.warning(self, "Ошибка", "Аватар уже запущен.")
            return

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen([sys.executable, "avatar.py", item.text()], creationflags=creationflags)
        self.refresh_avatar_status()

    def stop_avatar(self):
        if self.process:
            self.process.terminate()
            self.process = None
        self.refresh_avatar_status()

    def reset_to_defaults(self):
        item = self.preset_list.currentItem()
        if not item:
            return

        reply = QMessageBox.question(
            self,
            "Вернуть стандартные",
            f"Сбросить настройки пресета {item.text()} к стандартным значениям?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        default_config = self._default_config_template()
        current_device_index = None
        if self.config_data.get("Microphone"):
            current_device_index = self.config_data["Microphone"].get("DeviceIndex")
        default_config["Microphone"]["DeviceIndex"] = current_device_index

        self.config_data = default_config
        self._normalize_config_data()
        self._populate_sections()
        self.set_unsaved(True)


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        try:
            from PyQt5.QtWinExtras import QtWin

            QtWin.setCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except ImportError:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    window = PresetManager()
    window.show()
    sys.exit(app.exec_())
