import importlib
import os
import subprocess
import sys

from app_meta import APP_NAME, APP_VERSION

# Список обязательных библиотек
REQUIRED_LIBS = [
    "pygame",
    "numpy",
    "pyaudio",
    "pywin32",  # обязательно для Windows
]


def install_package(package):
    print(f"Устанавливаем {package}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    except subprocess.CalledProcessError:
        print(f"Не удалось установить {package}. Установите вручную.")
        sys.exit(1)


def check_and_install():
    print(f"Запуск {APP_NAME} v{APP_VERSION}")
    for lib in REQUIRED_LIBS:
        print(f"Проверка библиотеки: {lib}...")
        try:
            # Для pywin32 проверяем импорт win32api/win32gui.
            if lib == "pywin32":
                import win32api
                import win32gui
            else:
                importlib.import_module(lib)
        except ImportError:
            print(f"Библиотека {lib} не найдена. Устанавливаем...")
            install_package(lib)


if __name__ == "__main__":
    check_and_install()

    # Запуск main.pyw
    main_path = os.path.join(os.path.dirname(__file__), "main.pyw")
    if not os.path.exists(main_path):
        print("main.pyw не найден!")
        sys.exit(1)

    python_executable = sys.executable
    if sys.platform.startswith("win") and python_executable.endswith("python.exe"):
        python_executable = python_executable.replace("python.exe", "pythonw.exe")

    subprocess.Popen([python_executable, main_path])
