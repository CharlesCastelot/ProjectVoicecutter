import ctypes
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    _dpi = ctypes.windll.user32.GetDpiForSystem()
except Exception:
    _dpi = 96
_DPI_SCALE = _dpi / 96.0

CUSTOM_COMMANDS_FILE = "customCommands.json"
TRIGGER_COMMANDS_FILE = "triggerCommands.json"

# ─────────────────────────────────────────────────────────────────────────────
# Custom Commands Dialog
# ─────────────────────────────────────────────────────────────────────────────

class CustomCommandsDialog(tk.Toplevel):
    """Non-modal dialog for viewing, adding, and removing custom commands."""

    _BG       = "#0d0d1a"
    _BG2      = "#13132a"
    _BORDER   = "#222240"
    _FG       = "#dde0ff"
    _FG_DIM   = "#555577"
    _ACCENT   = "#44ee88"
    _ORANGE   = "#ffaa33"
    _RED      = "#ee4466"
    _ENTRY_BG = "#1a1a35"

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Custom Commands")
        self.configure(bg=self._BG)
        self.geometry(f"{int(540 * _DPI_SCALE)}x{int(520 * _DPI_SCALE)}")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Keep dialog above parent but not a true modal so voice keeps running
        self.transient(parent)

        self._type_var = tk.StringVar(value="script")
        self._build()
        self._load_commands()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #
    def _build(self):
        pad = {"padx": 18, "pady": 6}

        # ── Title ──────────────────────────────────────────────────────── #
        title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        tk.Label(self, text="Custom Commands", font=title_font,
                 fg=self._FG, bg=self._BG).pack(fill="x", padx=18, pady=(14, 2))
        tk.Frame(self, height=1, bg=self._BORDER).pack(fill="x", padx=18)

        # ── Existing commands list ─────────────────────────────────────── #
        section_font = tkfont.Font(family="Segoe UI", size=8)
        tk.Label(self, text="SAVED COMMANDS", font=section_font,
                 fg=self._FG_DIM, bg=self._BG, anchor="w").pack(fill="x", padx=20, pady=(8, 2))

        # Scrollable container
        list_outer = tk.Frame(self, bg=self._BG2, bd=0, highlightthickness=1,
                              highlightbackground=self._BORDER)
        list_outer.pack(fill="x", padx=18, pady=(0, 6))

        canvas = tk.Canvas(list_outer, bg=self._BG2, highlightthickness=0, height=190)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(canvas, bg=self._BG2)
        self._list_window = canvas.create_window((0, 0), window=self._list_frame, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self._list_window, width=canvas.winfo_width())

        self._list_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._list_window, width=e.width))
        self._canvas = canvas

        # ── Separator ─────────────────────────────────────────────────── #
        tk.Frame(self, height=1, bg=self._BORDER).pack(fill="x", padx=18, pady=(4, 0))

        # ── Add new command form ───────────────────────────────────────── #
        tk.Label(self, text="ADD NEW COMMAND", font=section_font,
                 fg=self._FG_DIM, bg=self._BG, anchor="w").pack(fill="x", padx=20, pady=(8, 2))

        form = tk.Frame(self, bg=self._BG)
        form.pack(fill="x", padx=18, pady=(0, 12))

        label_font = tkfont.Font(family="Segoe UI", size=10)
        entry_font = tkfont.Font(family="Segoe UI", size=10)

        # Keyword row
        kw_row = tk.Frame(form, bg=self._BG)
        kw_row.pack(fill="x", pady=3)
        tk.Label(kw_row, text="Keyword:", font=label_font, fg=self._FG_DIM,
                 bg=self._BG, width=10, anchor="w").pack(side="left")
        self._kw_entry = tk.Entry(kw_row, font=entry_font, bg=self._ENTRY_BG,
                                  fg=self._FG, insertbackground=self._FG,
                                  relief="flat", bd=4)
        self._kw_entry.pack(side="left", fill="x", expand=True)

        # Type row
        type_row = tk.Frame(form, bg=self._BG)
        type_row.pack(fill="x", pady=3)
        tk.Label(type_row, text="Type:", font=label_font, fg=self._FG_DIM,
                 bg=self._BG, width=10, anchor="w").pack(side="left")

        radio_font = tkfont.Font(family="Segoe UI", size=10)
        for value, label in (
            ("script", "Python Script"),
            ("effect", "Effect (drag)"),
            ("image",  "Click (hold)"),
        ):
            tk.Radiobutton(
                type_row, text=label, variable=self._type_var, value=value,
                font=radio_font, fg=self._FG, bg=self._BG,
                selectcolor=self._BG2, activebackground=self._BG,
                activeforeground=self._ACCENT,
                command=self._on_type_change,
            ).pack(side="left", padx=(0, 14))

        # Path row
        path_row = tk.Frame(form, bg=self._BG)
        path_row.pack(fill="x", pady=3)
        tk.Label(path_row, text="Path:", font=label_font, fg=self._FG_DIM,
                 bg=self._BG, width=10, anchor="w").pack(side="left")
        self._path_entry = tk.Entry(path_row, font=entry_font, bg=self._ENTRY_BG,
                                    fg=self._FG, insertbackground=self._FG,
                                    relief="flat", bd=4)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._browse_btn = tk.Button(
            path_row, text="Browse", font=label_font,
            bg=self._BG2, fg=self._FG, activebackground=self._BORDER,
            activeforeground=self._FG, relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=self._browse,
        )
        self._browse_btn.pack(side="left")

        # Accept Parameters checkbox — only visible when type == "script"
        self._accepts_params_var = tk.BooleanVar(value=False)
        self._params_row = tk.Frame(form, bg=self._BG)
        # (packed / forgotten dynamically in _on_type_change)
        tk.Label(self._params_row, text="", width=10, bg=self._BG).pack(side="left")
        tk.Checkbutton(
            self._params_row,
            text="Accept parameters after keyword",
            variable=self._accepts_params_var,
            font=label_font,
            fg=self._FG, bg=self._BG,
            selectcolor=self._BG2,
            activebackground=self._BG,
            activeforeground=self._ACCENT,
        ).pack(side="left")

        # Hint label (changes with type)
        self._hint_var = tk.StringVar(value='e.g. "run cleanup"  →  scripts/cleanup.py')
        hint_font = tkfont.Font(family="Segoe UI", size=8, slant="italic")
        tk.Label(form, textvariable=self._hint_var, font=hint_font,
                 fg=self._FG_DIM, bg=self._BG, anchor="w").pack(fill="x", pady=(0, 6))

        # Add button
        btn_row = tk.Frame(form, bg=self._BG)
        btn_row.pack(fill="x")
        add_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        tk.Button(
            btn_row, text="＋  Add Command", font=add_font,
            bg=self._ACCENT, fg="#000000", activebackground="#33cc77",
            activeforeground="#000000", relief="flat", bd=0,
            padx=14, pady=6, cursor="hand2",
            command=self._add_command,
        ).pack(side="right")

        # Apply initial visibility state (default type is "script" so params
        # checkbox should already be visible when the dialog first opens)
        self._on_type_change()

    # ------------------------------------------------------------------ #
    # Type change                                                          #
    # ------------------------------------------------------------------ #
    def _on_type_change(self):
        t = self._type_var.get()
        if t == "script":
            self._hint_var.set('e.g. "run cleanup"  →  customScripts/cleanup.py')
            self._params_row.pack(fill="x", pady=(0, 2))
        elif t == "effect":
            self._hint_var.set('e.g. "sharpen"  →  ImageReference/Effects/Sharpen.png  (keyword typed in Premiere search)')
            self._params_row.pack_forget()
            self._accepts_params_var.set(False)
        else:
            self._hint_var.set('e.g. "scale"  →  ImageReference/Click/scale.png  (click & hold blue value)')
            self._params_row.pack_forget()
            self._accepts_params_var.set(False)

    # ------------------------------------------------------------------ #
    # Load & render                                                        #
    # ------------------------------------------------------------------ #
    def _load_commands(self) -> dict:
        if not os.path.exists(CUSTOM_COMMANDS_FILE):
            data = {}
        else:
            try:
                with open(CUSTOM_COMMANDS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {}
        self._render_commands(data)
        return data

    def _render_commands(self, data: dict):
        # Clear existing rows
        for w in self._list_frame.winfo_children():
            w.destroy()

        row_font   = tkfont.Font(family="Segoe UI", size=10)
        badge_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        dim_font   = tkfont.Font(family="Segoe UI", size=9)

        if not data:
            tk.Label(self._list_frame, text="No custom commands yet.",
                     font=dim_font, fg=self._FG_DIM, bg=self._BG2,
                     pady=12).pack()
            return

        BADGE_COLORS = {
            "script": ("#1a3a2a", self._ACCENT),   # green
            "effect": ("#0f2035", "#44aaff"),        # blue
            "image":  ("#2a2a10", self._ORANGE),    # orange
            "hotkey": ("#2a1a3a", "#aa88ff"),        # purple
        }

        for keyword, cmd in sorted(data.items()):
            cmd_type = cmd.get("type", "hotkey") if isinstance(cmd, dict) else "hotkey"
            accepts_params = isinstance(cmd, dict) and cmd.get("accepts_params", False)
            path_str = (
                cmd.get("path", "") if isinstance(cmd, dict)
                else "+".join(cmd) if isinstance(cmd, list)
                else ""
            )

            row = tk.Frame(self._list_frame, bg=self._BG2)
            row.pack(fill="x", padx=6, pady=2)

            # Type badge — append "+p" for parameterised scripts
            bg_c, fg_c = BADGE_COLORS.get(cmd_type, ("#1a1a2a", self._FG_DIM))
            badge_text = cmd_type.upper() + (" +p" if accepts_params else "")
            tk.Label(row, text=badge_text, font=badge_font,
                     fg=fg_c, bg=bg_c, padx=5, pady=2).pack(side="left", padx=(0, 8))

            # Keyword + path
            tk.Label(row, text=f'"{keyword}"', font=row_font,
                     fg=self._FG, bg=self._BG2, anchor="w").pack(side="left")
            tk.Label(row, text=f"  →  {path_str}", font=dim_font,
                     fg=self._FG_DIM, bg=self._BG2, anchor="w").pack(side="left", fill="x", expand=True)

            # Remove button
            tk.Button(
                row, text="✕", font=badge_font,
                bg=self._BG2, fg=self._RED, activebackground=self._BG2,
                activeforeground="#ff6688", relief="flat", bd=0,
                padx=8, pady=2, cursor="hand2",
                command=lambda kw=keyword: self._remove_command(kw),
            ).pack(side="right")

    # ------------------------------------------------------------------ #
    # Browse                                                               #
    # ------------------------------------------------------------------ #
    def _browse(self):
        t = self._type_var.get()
        if t == "script":
            path = filedialog.askopenfilename(
                parent=self,
                title="Select Python script",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")],
                initialdir="customScripts",
            )
        elif t == "effect":
            path = filedialog.askopenfilename(
                parent=self,
                title="Select effect image (ImageReference/Effects/)",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.bmp"),
                    ("All files", "*.*"),
                ],
                initialdir="ImageReference/Effects",
            )
        else:  # "image" / click-hold
            path = filedialog.askopenfilename(
                parent=self,
                title="Select click image (ImageReference/Click/)",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.bmp"),
                    ("All files", "*.*"),
                ],
                initialdir="ImageReference/Click",
            )

        if path:
            # Store relative path when inside the project folder
            try:
                rel = os.path.relpath(path)
                path = rel
            except ValueError:
                pass  # Different drive — keep absolute
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, path)

    # ------------------------------------------------------------------ #
    # DPI version generation                                              #
    # ------------------------------------------------------------------ #
    def _generate_dpi_versions(self, src_path: str, cmd_type: str) -> str:
        """Copy src image to the base folder and generate all 6 DPI-scaled versions.

        Returns the relative path to the base-folder copy (stored in JSON).
        The DPI-specific copies are written to ImageReference/DPI_xxx/<subfolder>/
        so find_on_screen_from_path() can auto-select the right scale at runtime.
        """
        import shutil
        import cv2 as _cv2

        subfolder = "Effects" if cmd_type == "effect" else "Click"
        base_dir  = os.path.join("ImageReference", subfolder)
        os.makedirs(base_dir, exist_ok=True)

        filename = os.path.basename(src_path)
        base_dest = os.path.join(base_dir, filename)

        # Copy original to base folder (skip if already there)
        if os.path.abspath(src_path) != os.path.abspath(base_dest):
            shutil.copy2(src_path, base_dest)

        # Detect the DPI scale of the monitor where Premiere is running —
        # that is the scale at which the user captured the source image.
        try:
            import image_matcher as _im
            current_scale = _im.get_premiere_dpi_scale()
        except Exception:
            current_scale = 1.0

        src_img = _cv2.imread(src_path)
        if src_img is None:
            return base_dest

        src_h, src_w = src_img.shape[:2]

        dpi_map = [
            (1.00, "DPI_100"),
            (1.25, "DPI_125"),
            (1.50, "DPI_150"),
            (1.75, "DPI_175"),
            (2.00, "DPI_200"),
            (2.25, "DPI_225"),
        ]

        generated = []
        for target_scale, dpi_folder in dpi_map:
            factor  = target_scale / current_scale
            new_w   = max(1, int(round(src_w * factor)))
            new_h   = max(1, int(round(src_h * factor)))

            if abs(new_w - src_w) <= 1 and abs(new_h - src_h) <= 1:
                resized = src_img
            elif factor < 1.0:
                resized = _cv2.resize(src_img, (new_w, new_h),
                                      interpolation=_cv2.INTER_AREA)
            else:
                resized = _cv2.resize(src_img, (new_w, new_h),
                                      interpolation=_cv2.INTER_LANCZOS4)

            dest_dir  = os.path.join("ImageReference", dpi_folder, subfolder)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, filename)
            _cv2.imwrite(dest_path, resized)
            generated.append(dpi_folder)

        print(f"[ui] DPI versions generated for '{filename}': {', '.join(generated)}")
        return base_dest

    # ------------------------------------------------------------------ #
    # Add                                                                  #
    # ------------------------------------------------------------------ #
    def _add_command(self):
        keyword = self._kw_entry.get().strip().lower()
        path    = self._path_entry.get().strip()
        cmd_type = self._type_var.get()

        if not keyword:
            messagebox.showwarning("Missing keyword",
                                   "Please enter a keyword.", parent=self)
            return
        if not path:
            messagebox.showwarning("Missing path",
                                   "Please enter or browse to a file path.", parent=self)
            return

        data = self._read_json()
        if keyword in data:
            if not messagebox.askyesno(
                "Overwrite?",
                f'"{keyword}" already exists. Replace it?', parent=self
            ):
                return

        # For image-based commands, copy to the base folder and generate all
        # DPI-scaled versions so find_on_screen_from_path() auto-selects the
        # right scale without a multi-scale sweep.
        if cmd_type in ("effect", "image"):
            try:
                path = self._generate_dpi_versions(path, cmd_type)
            except Exception as exc:
                messagebox.showwarning(
                    "DPI generation failed",
                    f"Could not generate DPI versions:\n{exc}\n\n"
                    "Command saved with original path.",
                    parent=self,
                )

        entry: dict = {"type": cmd_type, "path": path}
        if cmd_type == "script" and self._accepts_params_var.get():
            entry["accepts_params"] = True
        data[keyword] = entry
        self._write_json(data)

        # Clear form
        self._kw_entry.delete(0, "end")
        self._path_entry.delete(0, "end")
        self._render_commands(data)

    # ------------------------------------------------------------------ #
    # Remove                                                               #
    # ------------------------------------------------------------------ #
    def _remove_command(self, keyword: str):
        if not messagebox.askyesno(
            "Remove command",
            f'Remove "{keyword}"?', parent=self
        ):
            return
        data = self._read_json()
        data.pop(keyword, None)
        self._write_json(data)
        self._render_commands(data)

    # ------------------------------------------------------------------ #
    # JSON helpers                                                         #
    # ------------------------------------------------------------------ #
    def _read_json(self) -> dict:
        if not os.path.exists(CUSTOM_COMMANDS_FILE):
            return {}
        try:
            with open(CUSTOM_COMMANDS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_json(self, data: dict):
        with open(CUSTOM_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


# ─────────────────────────────────────────────────────────────────────────────
# Trigger Commands Dialog
# ─────────────────────────────────────────────────────────────────────────────

class TriggerCommandsDialog(tk.Toplevel):
    """Non-modal dialog for viewing, adding, and removing trigger commands."""

    _BG       = "#0d0d1a"
    _BG2      = "#13132a"
    _BORDER   = "#222240"
    _FG       = "#dde0ff"
    _FG_DIM   = "#555577"
    _ACCENT   = "#44ee88"
    _ORANGE   = "#ffaa33"
    _RED      = "#ee4466"
    _ENTRY_BG = "#1a1a35"

    def __init__(self, parent: tk.Tk, on_change=None):
        super().__init__(parent)
        self.title("Trigger Commands")
        self.configure(bg=self._BG)
        self.geometry(f"{int(560 * _DPI_SCALE)}x{int(580 * _DPI_SCALE)}")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(parent)
        self._on_change = on_change
        self._build()
        self._load()

    def _build(self):
        title_font   = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        section_font = tkfont.Font(family="Segoe UI", size=8)
        label_font   = tkfont.Font(family="Segoe UI", size=10)
        entry_font   = tkfont.Font(family="Segoe UI", size=10)
        hint_font    = tkfont.Font(family="Segoe UI", size=8, slant="italic")
        add_font     = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        tk.Label(self, text="Trigger Commands", font=title_font,
                 fg=self._FG, bg=self._BG).pack(fill="x", padx=18, pady=(14, 2))
        tk.Frame(self, height=1, bg=self._BORDER).pack(fill="x", padx=18)

        tk.Label(self, text="SAVED TRIGGERS", font=section_font,
                 fg=self._FG_DIM, bg=self._BG, anchor="w").pack(fill="x", padx=20, pady=(8, 2))

        list_outer = tk.Frame(self, bg=self._BG2, bd=0,
                              highlightthickness=1, highlightbackground=self._BORDER)
        list_outer.pack(fill="x", padx=18, pady=(0, 6))

        canvas = tk.Canvas(list_outer, bg=self._BG2, highlightthickness=0, height=180)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(canvas, bg=self._BG2)
        self._list_win = canvas.create_window((0, 0), window=self._list_frame, anchor="nw")

        def _on_cfg(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self._list_win, width=canvas.winfo_width())

        self._list_frame.bind("<Configure>", _on_cfg)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._list_win, width=e.width))

        tk.Frame(self, height=1, bg=self._BORDER).pack(fill="x", padx=18, pady=(4, 0))

        tk.Label(self, text="ADD NEW TRIGGER", font=section_font,
                 fg=self._FG_DIM, bg=self._BG, anchor="w").pack(fill="x", padx=20, pady=(8, 2))

        form = tk.Frame(self, bg=self._BG)
        form.pack(fill="x", padx=18, pady=(0, 12))

        def _row(label_text):
            row = tk.Frame(form, bg=self._BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label_text, font=label_font, fg=self._FG_DIM,
                     bg=self._BG, width=14, anchor="w").pack(side="left")
            e = tk.Entry(row, font=entry_font, bg=self._ENTRY_BG, fg=self._FG,
                         insertbackground=self._FG, relief="flat", bd=4)
            e.pack(side="left", fill="x", expand=True)
            return e

        self._word_entry = _row("Trigger word:")
        self._desc_entry = _row("Description:")

        path_row = tk.Frame(form, bg=self._BG)
        path_row.pack(fill="x", pady=3)
        tk.Label(path_row, text="Script path:", font=label_font, fg=self._FG_DIM,
                 bg=self._BG, width=14, anchor="w").pack(side="left")
        self._path_entry = tk.Entry(path_row, font=entry_font, bg=self._ENTRY_BG,
                                    fg=self._FG, insertbackground=self._FG,
                                    relief="flat", bd=4)
        self._path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(path_row, text="Browse", font=label_font,
                  bg=self._BG2, fg=self._FG, activebackground=self._BORDER,
                  activeforeground=self._FG, relief="flat", bd=0,
                  padx=10, pady=4, cursor="hand2",
                  command=self._browse).pack(side="left")

        tk.Label(form,
                 text='Say the trigger word followed by any text → your script receives\n'
                      'that text as sys.argv[1].  e.g. "marker chapel intro" → argv[1] = "chapel intro"',
                 font=hint_font, fg=self._FG_DIM, bg=self._BG, anchor="w",
                 justify="left").pack(fill="x", pady=(2, 6))

        btn_row = tk.Frame(form, bg=self._BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="＋  Add Trigger", font=add_font,
                  bg=self._ACCENT, fg="#000000", activebackground="#33cc77",
                  activeforeground="#000000", relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  command=self._add).pack(side="right")

    def _load(self):
        data = self._read_json()
        self._render(data)

    def _render(self, data: dict):
        for w in self._list_frame.winfo_children():
            w.destroy()

        row_font   = tkfont.Font(family="Segoe UI", size=10)
        badge_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        dim_font   = tkfont.Font(family="Segoe UI", size=9)

        entries = {k: v for k, v in data.items() if not k.startswith("_")}

        if not entries:
            tk.Label(self._list_frame, text="No trigger commands yet.",
                     font=dim_font, fg=self._FG_DIM, bg=self._BG2,
                     pady=12).pack()
            return

        for word, cfg in sorted(entries.items()):
            path = cfg.get("path", "—")
            desc = cfg.get("description", "")

            row = tk.Frame(self._list_frame, bg=self._BG2)
            row.pack(fill="x", padx=6, pady=2)

            tk.Label(row, text="TRIGGER", font=badge_font,
                     fg=self._ORANGE, bg="#2a2a10",
                     padx=5, pady=2).pack(side="left", padx=(0, 8))

            tk.Label(row, text=f'"{word}"', font=row_font,
                     fg=self._FG, bg=self._BG2).pack(side="left")

            tk.Label(row,
                     text=f"  →  {path}" + (f"  — {desc}" if desc else ""),
                     font=dim_font, fg=self._FG_DIM,
                     bg=self._BG2, anchor="w").pack(side="left", fill="x", expand=True)

            tk.Button(row, text="✕", font=badge_font,
                      bg=self._BG2, fg=self._RED,
                      activebackground=self._BG2, activeforeground="#ff6688",
                      relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                      command=lambda w=word: self._remove(w)).pack(side="right")

    def _browse(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Python script",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
        )
        if path:
            try:
                path = os.path.relpath(path)
            except ValueError:
                pass
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, path)

    def _add(self):
        word = self._word_entry.get().strip().lower()
        path = self._path_entry.get().strip()
        desc = self._desc_entry.get().strip()

        if not word:
            messagebox.showwarning("Missing trigger word",
                                   "Please enter a trigger word.", parent=self)
            return
        if not path:
            messagebox.showwarning("Missing script path",
                                   "Please enter or browse to a Python script.", parent=self)
            return

        data = self._read_json()
        if word in data and not word.startswith("_"):
            if not messagebox.askyesno("Overwrite?",
                                       f'"{word}" already exists. Replace it?',
                                       parent=self):
                return

        entry = {"path": path}
        if desc:
            entry["description"] = desc

        data[word] = entry
        self._write_json(data)

        self._word_entry.delete(0, "end")
        self._path_entry.delete(0, "end")
        self._desc_entry.delete(0, "end")
        self._render(data)

    def _remove(self, word: str):
        if not messagebox.askyesno("Remove trigger",
                                   f'Remove "{word}"?', parent=self):
            return
        data = self._read_json()
        data.pop(word, None)
        self._write_json(data)
        self._render(data)

    def _read_json(self) -> dict:
        if not os.path.exists(TRIGGER_COMMANDS_FILE):
            return {}
        try:
            with open(TRIGGER_COMMANDS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_json(self, data: dict):
        with open(TRIGGER_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        if self._on_change:
            self._on_change()


# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────

class VoiceCutterUI:
    def __init__(self, wake_word: str = "computer"):
        self.wake_word = wake_word
        self._queue: queue.Queue = queue.Queue()
        self._clear_job = None
        self._cmd_dialog: CustomCommandsDialog | None = None
        self._trigger_dialog: TriggerCommandsDialog | None = None

        # Command history: list of (user_said, command_ran) tuples, newest first
        self._command_history: list[tuple[str, str]] = []

        self.root = tk.Tk()
        self.root.title("VoiceCutter")
        self.root.configure(bg="#0d0d1a")
        self.root.tk.call('tk', 'scaling', _dpi / 72.0)
        self.root.geometry(f"{int(520 * _DPI_SCALE)}x{int(500 * _DPI_SCALE)}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._build()

    # ------------------------------------------------------------------ #
    # Build UI                                                             #
    # ------------------------------------------------------------------ #
    def _build(self):
        # --- Greeting -------------------------------------------------- #
        greeting_font = tkfont.Font(family="Segoe UI", size=13)
        tk.Label(
            self.root,
            text=f'Hello, just say "{self.wake_word}" to get started',
            font=greeting_font,
            fg="#8888aa",
            bg="#0d0d1a",
            wraplength=480,
            pady=12,
        ).pack(fill="x", padx=20)

        # --- Separator ------------------------------------------------- #
        tk.Frame(self.root, height=1, bg="#222240").pack(fill="x", padx=20)

        # --- Transcript display ---------------------------------------- #
        transcript_font = tkfont.Font(family="Segoe UI", size=16)
        self._transcript_var = tk.StringVar(value="")
        tk.Label(
            self.root,
            textvariable=self._transcript_var,
            font=transcript_font,
            fg="#dde0ff",
            bg="#0d0d1a",
            wraplength=480,
            justify="center",
            pady=6,
        ).pack(fill="x", padx=20)

        # --- Command History ------------------------------------------- #
        tk.Frame(self.root, height=1, bg="#222240").pack(fill="x", padx=20, pady=(4, 0))

        history_title_font = tkfont.Font(family="Segoe UI", size=9)
        tk.Label(
            self.root,
            text="COMMAND HISTORY",
            font=history_title_font,
            fg="#555577",
            bg="#0d0d1a",
            anchor="w",
        ).pack(fill="x", padx=24, pady=(4, 0))

        self._history_frame = tk.Frame(self.root, bg="#0d0d1a")
        self._history_frame.pack(fill="x", padx=24, pady=(0, 4))

        # Pre-create 8 label pairs for command history rows
        self._history_labels: list[tuple[tk.Label, tk.Label]] = []
        hist_font = tkfont.Font(family="Segoe UI", size=10)
        hist_font_bold = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        for i in range(8):
            row = tk.Frame(self._history_frame, bg="#0d0d1a")
            row.pack(fill="x", pady=1)
            said_label = tk.Label(
                row,
                text="",
                font=hist_font_bold if i == 0 else hist_font,
                fg="#dde0ff" if i == 0 else "#555577",
                bg="#0d0d1a",
                anchor="w",
            )
            said_label.pack(side="left")
            ran_label = tk.Label(
                row,
                text="",
                font=hist_font_bold if i == 0 else hist_font,
                fg="#44ee88" if i == 0 else "#3a6648",
                bg="#0d0d1a",
                anchor="e",
            )
            ran_label.pack(side="right")
            self._history_labels.append((said_label, ran_label))

        # --- Trigger Commands ------------------------------------------ #
        tk.Frame(self.root, height=1, bg="#222240").pack(fill="x", padx=20, pady=(4, 0))

        trigger_title_font = tkfont.Font(family="Segoe UI", size=9)
        tk.Label(
            self.root,
            text="TRIGGER COMMANDS",
            font=trigger_title_font,
            fg="#555577",
            bg="#0d0d1a",
            anchor="w",
        ).pack(fill="x", padx=24, pady=(4, 0))

        self._trigger_frame = tk.Frame(self.root, bg="#0d0d1a")
        self._trigger_frame.pack(fill="x", padx=24, pady=(2, 4))
        self._refresh_triggers()

        # --- Status bar ------------------------------------------------ #
        status_frame = tk.Frame(self.root, bg="#0a0a16", pady=14)
        status_frame.pack(fill="x", side="bottom")

        self._dot_canvas = tk.Canvas(
            status_frame, width=14, height=14, bg="#0a0a16", highlightthickness=0
        )
        self._dot_canvas.pack(side="left", padx=(20, 8))
        self._dot = self._dot_canvas.create_oval(1, 1, 13, 13, fill="#444460", outline="")

        status_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self._status_var = tk.StringVar(value="SLEEPING")
        self._status_label = tk.Label(
            status_frame,
            textvariable=self._status_var,
            font=status_font,
            fg="#444460",
            bg="#0a0a16",
        )
        self._status_label.pack(side="left")

        # ＋ button — opens Custom Commands dialog
        plus_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        tk.Button(
            status_frame,
            text="＋",
            font=plus_font,
            bg="#0a0a16",
            fg="#555577",
            activebackground="#0a0a16",
            activeforeground="#44ee88",
            relief="flat",
            bd=0,
            padx=10,
            cursor="hand2",
            command=self._open_custom_commands,
        ).pack(side="right", padx=(0, 4))

        # ⚡ button — opens Trigger Commands dialog
        tk.Button(
            status_frame,
            text="⚡",
            font=plus_font,
            bg="#0a0a16",
            fg="#555577",
            activebackground="#0a0a16",
            activeforeground="#ffaa33",
            relief="flat",
            bd=0,
            padx=10,
            cursor="hand2",
            command=self._open_trigger_commands,
        ).pack(side="right", padx=(0, 16))

    # ------------------------------------------------------------------ #
    # Custom + Trigger Commands dialogs                                    #
    # ------------------------------------------------------------------ #
    def _refresh_triggers(self):
        """Re-read triggerCommands.json and redraw the trigger chips."""
        for w in self._trigger_frame.winfo_children():
            w.destroy()

        chip_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        key_font  = tkfont.Font(family="Segoe UI", size=9)

        try:
            if os.path.exists(TRIGGER_COMMANDS_FILE):
                with open(TRIGGER_COMMANDS_FILE, encoding="utf-8") as f:
                    data = {k: v for k, v in json.load(f).items()
                            if not k.startswith("_")}
            else:
                data = {}
        except Exception:
            data = {}

        if not data:
            tkfont_dim = tkfont.Font(family="Segoe UI", size=9)
            tk.Label(self._trigger_frame, text="No triggers set.",
                     font=tkfont_dim, fg="#555577", bg="#0d0d1a").pack(side="left")
            return

        for word, cfg in sorted(data.items()):
            script = os.path.basename(cfg.get("path", "?"))
            chip = tk.Frame(self._trigger_frame, bg="#2a2a10", padx=6, pady=2)
            chip.pack(side="left", padx=(0, 6), pady=1)
            tk.Label(chip, text=word, font=chip_font,
                     fg="#ffaa33", bg="#2a2a10").pack(side="left")
            tk.Label(chip, text=f" → {script}", font=key_font,
                     fg="#888866", bg="#2a2a10").pack(side="left")

    def _open_custom_commands(self):
        # If the dialog is already open, just bring it to front
        if self._cmd_dialog and self._cmd_dialog.winfo_exists():
            self._cmd_dialog.lift()
            self._cmd_dialog.focus_force()
            return
        self._cmd_dialog = CustomCommandsDialog(self.root)

    def _open_trigger_commands(self):
        if self._trigger_dialog and self._trigger_dialog.winfo_exists():
            self._trigger_dialog.lift()
            self._trigger_dialog.focus_force()
            return
        self._trigger_dialog = TriggerCommandsDialog(self.root,
                                                     on_change=self._refresh_triggers)

    # ------------------------------------------------------------------ #
    # Command history                                                      #
    # ------------------------------------------------------------------ #
    def add_command_history(self, user_said: str, command_ran: str):
        """Thread-safe: add a command to history via the queue."""
        self._queue.put(("history", (user_said, command_ran)))

    def _apply_history(self, user_said: str, command_ran: str):
        self._command_history.insert(0, (user_said, command_ran))
        self._command_history = self._command_history[:8]
        self._refresh_history_labels()

    def _refresh_history_labels(self):
        hist_font = tkfont.Font(family="Segoe UI", size=10)
        hist_font_bold = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        for i, (said_label, ran_label) in enumerate(self._history_labels):
            if i < len(self._command_history):
                user_said, cmd_ran = self._command_history[i]
                said_label.config(
                    text=f'"{user_said}"',
                    font=hist_font_bold if i == 0 else hist_font,
                    fg="#dde0ff" if i == 0 else "#555577",
                )
                ran_label.config(
                    text=f"-> {cmd_ran}",
                    font=hist_font_bold if i == 0 else hist_font,
                    fg="#44ee88" if i == 0 else "#3a6648",
                )
            else:
                said_label.config(text="")
                ran_label.config(text="")

    # ------------------------------------------------------------------ #
    # Thread-safe public API                                               #
    # ------------------------------------------------------------------ #
    def set_sleeping(self):
        self._queue.put(("sleeping", None))

    def set_listening(self):
        self._queue.put(("listening", None))

    def set_write_mode(self, active: bool):
        self._queue.put(("write_mode", active))

    def set_transcript(self, text: str, auto_clear_ms: int = 4000):
        self._queue.put(("transcript", (text, auto_clear_ms)))

    # ------------------------------------------------------------------ #
    # Internal queue pump (runs on main thread via after())               #
    # ------------------------------------------------------------------ #
    def _pump(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "sleeping":
                    self._apply_sleeping()
                elif kind == "listening":
                    self._apply_listening()
                elif kind == "transcript":
                    text, delay = payload
                    self._apply_transcript(text, delay)
                elif kind == "write_mode":
                    self._apply_write_mode(payload)
                elif kind == "history":
                    user_said, command_ran = payload
                    self._apply_history(user_said, command_ran)
        except queue.Empty:
            pass
        self.root.after(40, self._pump)

    def _apply_sleeping(self):
        self._status_var.set("SLEEPING")
        self._status_label.config(fg="#444460")
        self._dot_canvas.itemconfig(self._dot, fill="#444460")
        self._transcript_var.set("")
        if self._clear_job:
            self.root.after_cancel(self._clear_job)
            self._clear_job = None

    def _apply_listening(self):
        self._status_var.set("LISTENING")
        self._status_label.config(fg="#44ee88")
        self._dot_canvas.itemconfig(self._dot, fill="#44ee88")

    def _apply_write_mode(self, active: bool):
        if active:
            self._status_var.set("WRITING")
            self._status_label.config(fg="#ffaa33")
            self._dot_canvas.itemconfig(self._dot, fill="#ffaa33")
        else:
            self._status_var.set("LISTENING")
            self._status_label.config(fg="#44ee88")
            self._dot_canvas.itemconfig(self._dot, fill="#44ee88")

    def _apply_transcript(self, text: str, delay: int):
        self._transcript_var.set(text)
        if self._clear_job:
            self.root.after_cancel(self._clear_job)
        self._clear_job = self.root.after(delay, lambda: self._transcript_var.set(""))

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #
    def run(self, voice_fn):
        """Start the voice loop in a daemon thread, then enter the tk main loop."""
        threading.Thread(target=voice_fn, daemon=True).start()
        self.root.after(40, self._pump)
        self.root.mainloop()
