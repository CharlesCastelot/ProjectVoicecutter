# Project Voicecutter

A voice command system for Adobe Premiere Pro on Windows. Speak commands into your microphone to cut, trim, apply effects, add markers, search the timeline, and more — all hands-free while Premiere is open.

---

## Requirements

- **Windows 10 or 11** (this project is Windows-only)
- **Adobe Premiere Pro** installed and open while running
- **Python 3.14+**
- **uv** (Python package manager)
- **An NVIDIA GPU** (strongly recommended — see CUDA note below)

---

## Installation

### 1. Install uv

If you don't have `uv` yet:

```
pip install uv
```

Or use the official installer: https://docs.astral.sh/uv/getting-started/installation/

### 2. Clone the repository

```
git clone https://github.com/CharlesCastelot/ProjectVoicecutter.git
cd ProjectVoicecutter
```

### 3. Install all dependencies

```
uv sync
```

This creates a `.venv` folder and installs every dependency listed in `pyproject.toml` automatically, including the CUDA runtime DLLs (no separate CUDA download needed for the Python packages).

### 4. Download the Vosk speech model

The offline command-recognition engine requires a model file that is not included in the repo (~68 MB).

1. Go to: https://alphacephei.com/vosk/models
2. Download **`vosk-model-small-en-us-0.15`**
3. Unzip it so you have a folder named exactly **`vosk-model-small-en-us`** sitting in the project root:

```
ProjectVoicecutter/
├── vosk-model-small-en-us/   ← must be here
│   ├── am/
│   ├── conf/
│   ├── graph/
│   └── ...
├── main.py
└── ...
```

---

## ⚠️ CUDA / GPU Warning

This project uses **faster-whisper** for speech transcription, which runs significantly faster on an NVIDIA GPU.

- The `uv sync` step installs the CUDA 12 runtime DLLs automatically via PyPI packages — **you do not need to install the full CUDA Toolkit separately**.
- However, **you do need an NVIDIA GPU that supports CUDA 12** for GPU acceleration to work.
- If you have no NVIDIA GPU, faster-whisper will automatically fall back to CPU mode, which is slower but still functional. Expect a noticeable delay after each voice command.

If you see errors mentioning `cublas`, `cudnn`, or `ctranslate2` on startup, your GPU may not support CUDA 12. In that case you can remove the three `nvidia-*` lines from `pyproject.toml` and re-run `uv sync`.

---

## Running

Activate the virtual environment first:

```
.venv\Scripts\activate
```

Then launch:

```
python main.py
```

Or, without activating the venv:

```
uv run python main.py
```

Make sure **Adobe Premiere Pro is open** before starting — the script needs to detect and control the Premiere window.

---

## First-Time Calibration

On the first run, the tool needs to learn where two UI elements are on **your** screen. A fullscreen overlay will appear asking you to click:

1. **The Effects panel search box** — the search bar inside Premiere's Effects panel
2. **The Find/Search bar** — used by the `search` voice command

These coordinates are saved locally and reused automatically. If your Premiere layout ever changes, say:
- **"recalibrate"** — re-picks the Effects panel search box
- **"recalibrate search"** — re-picks the Find bar

---

## Usage

Once running, speak commands clearly into your microphone. Examples:

| Voice Command | Action |
|---|---|
| `"cut"` | Razor cut at playhead |
| `"undo"` | Ctrl+Z |
| `"cross dissolve"` | Applies Cross Dissolve to your last-clicked edit point |
| `"marker chapter one"` | Adds a labeled marker at the playhead |
| `"red chapter one"` | Adds a red colored marker labeled "chapter one" |
| `"search interview"` | Types "interview" into the Find bar |
| `"recalibrate"` | Re-runs the Effects panel click calibration |

For a full list of commands, see `allowedCommands.py`.
