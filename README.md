<table>
  <tr>
    <td width="96" valign="middle">
      <img src="docs/png2bicon.png" alt="PNG2B logo" width="80">
    </td>
    <td valign="middle">
      <h1 style="margin: 0;">PNG2B Readme</h1>
    </td>
  </tr>
</table>

## About

PNG2B is a Windows-focused PNG avatar tool with a preset manager and a real-time avatar runner.
The project uses `PyQt5` for the preset editor and `pygame` + `pyaudio` for avatar rendering and microphone-driven animation.

Current app metadata:

- Name: `PNG2B`
- Version: `2.5`
- Main launcher: [`run.pyw`](run.pyw)
- Preset manager: [`main.pyw`](main.pyw)
- Avatar runtime: [`avatar.py`](avatar.py)

## Features

- Preset manager with editable avatar, microphone, lip sync, blink, movement, and mouth settings
- Real-time microphone level monitor inside the preset manager
- Avatar runtime with lip sync, blink, emotional blink, and movement modes
- Preset storage in the new structure: `presets/<PresetName>/config.json` and `presets/<PresetName>/avatar/...`
- Shared app metadata in [`app_meta.py`](app_meta.py)
- Shared preset path configuration in [`app_paths.py`](app_paths.py)

## Requirements

The launcher currently checks and installs these Python packages automatically:

- `pygame`
- `numpy`
- `pyaudio`
- `pywin32`

The app is currently built around Windows behavior:

- `pywin32` is used for layered window behavior and top-most window handling
- `run.pyw` switches from `python.exe` to `pythonw.exe` on Windows

## Run

Start the project with:

```powershell
python run.pyw
```

What happens on startup:

1. `run.pyw` checks required libraries.
2. Missing libraries are installed through `pip`.
3. The preset manager from `main.pyw` is launched.

## Preset Structure

Each preset lives in:

```text
presets/
  <PresetName>/
    config.json
    avatar/
      s_0.png
      s_1.png
      ...
      b_0.png
      eb_0.png
      cm.png
```

Notes:

- `config.json` stores window, microphone, lip sync, blink, movement, and mouth settings.
- `avatar/` stores the sprite assets used by `avatar.py`.
- The current code still contains legacy fallback paths for `Prissets` / `Prisset`, but the project now uses `presets/` as the primary location.

## Project Files

- [`run.pyw`](run.pyw): startup script and dependency bootstrapper
- [`main.pyw`](main.pyw): preset manager UI
- [`avatar.py`](avatar.py): avatar renderer and microphone-reactive runtime
- [`app_meta.py`](app_meta.py): app name, version, and window title metadata
- [`app_paths.py`](app_paths.py): shared preset directory and file-name constants
- [`presets`](presets): active presets in the new structure
- [`docs/png2bicon.png`](docs/png2bicon.png): logo used in this README

## Current State

The repository already contains at least one migrated preset:

- [`presets/SlipperOff/config.json`](presets/SlipperOff/config.json)
- [`presets/SlipperOff/avatar`](presets/SlipperOff/avatar)
