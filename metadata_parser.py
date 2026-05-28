"""
Metadata command parser for Adobe Premiere Pro voice automation.
Standalone — no imports from the main voice assistant codebase.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent / "shot_configs"
DEFAULT_CONFIG = "default"

# ── Column profiles ───────────────────────────────────────────────────────────

PROFILES: dict[str, list[str]] = {
    "basic": ["scene", "take", "camera"],
    "full":  ["scene", "take", "camera", "description", "location", "character", "notes"],
}

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class MetadataRow:
    scene:       str = ""
    take:        str = ""
    camera:      str = ""
    description: str = ""
    location:    str = ""
    character:   str = ""
    notes:       str = ""


@dataclass
class ParseResult:
    rows:    list[MetadataRow]
    columns: list[str]  # only columns in the command — what the UI writer should touch


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.json"
    if not path.exists():
        path = CONFIG_DIR / f"{DEFAULT_CONFIG}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Sticky store ──────────────────────────────────────────────────────────────

class MetadataStore:
    def __init__(self):
        self._fields:    dict[str, str] = {}
        self.profile:    str  = "basic"
        self.config_name: str = DEFAULT_CONFIG
        self._config:    dict = _load_config(DEFAULT_CONFIG)

    def set_base(self, fields: dict[str, str]) -> None:
        self._fields.update({k: v for k, v in fields.items() if v})

    def get(self, key: str) -> str:
        return self._fields.get(key, "")

    def build_row(self, overrides: dict[str, str] | None = None) -> MetadataRow:
        merged = {**self._fields, **(overrides or {})}
        return MetadataRow(**{k: merged.get(k, "") for k in MetadataRow.__dataclass_fields__})

    def set_profile(self, name: str) -> None:
        if name in PROFILES:
            self.profile = name

    def set_config(self, name: str) -> bool:
        path = CONFIG_DIR / f"{name}.json"
        if path.exists():
            self.config_name = name
            self._config = _load_config(name)
            return True
        return False

    def get_columns(self) -> list[str]:
        return PROFILES.get(self.profile, PROFILES["basic"])

    @property
    def config(self) -> dict:
        return self._config


# ── Range expansion ───────────────────────────────────────────────────────────

def _numeric_range(start: int, end: int) -> list[str]:
    return [str(i) for i in range(start, end + 1)]


def _letter_range(start: str, end: str) -> list[str]:
    return [chr(c) for c in range(ord(start.upper()), ord(end.upper()) + 1)]


# ── Description formatting ────────────────────────────────────────────────────

def _apply_case(text: str, case: str) -> str:
    return {"upper": str.upper, "lower": str.lower, "title": str.title}.get(case, lambda x: x)(text)


def format_description(text: str, config: dict) -> str:
    if not text:
        return ""
    shots     = config.get("shots", {})
    separator = config.get("separator", "_")
    case      = config.get("case", "title")
    fmt       = config.get("description_format", "{shot}{separator}{description}")

    for key in sorted(shots, key=len, reverse=True):
        if text.lower().startswith(key.lower()):
            shot_word = _apply_case(shots[key], case)
            remainder = text[len(key):].strip()
            if remainder:
                return fmt.format(
                    shot=shot_word,
                    separator=separator,
                    description=_apply_case(remainder, case),
                )
            return shot_word

    return _apply_case(text, case)


# ── Tokenizer ─────────────────────────────────────────────────────────────────

_KEYWORD_MAP: dict[str, str] = {
    "scene":  "scene",
    "take":   "take",
    "takes":  "take",
    "cam":    "camera",
    "desc":   "description",
    "loc":    "location",
    "char":   "character",
    "notes":  "notes",
}

_NUM = re.compile(r"^\d+$")
_LET = re.compile(r"^[A-Za-z]$")


def _tokenize(text: str) -> tuple[dict, list[str]]:
    """
    Walk tokens left-to-right. Each keyword consumes exactly the tokens it needs:
      scene  → 1 token
      take   → 1 token, or 3 tokens (N through M)
      cam    → 1 token (letter), or 3 tokens (A through B)
      others → all tokens until next keyword
    Orphan tokens (no preceding keyword) become description.

    Returns (fields_dict, active_columns_in_order).
    """
    tokens = text.split()
    fields:  dict       = {}
    active:  list[str]  = []
    orphans: list[str]  = []
    i = 0

    while i < len(tokens):
        tok = tokens[i].lower()

        if tok not in _KEYWORD_MAP:
            orphans.append(tokens[i])
            i += 1
            continue

        field = _KEYWORD_MAP[tok]
        if field not in active:
            active.append(field)
        i += 1

        if field == "scene":
            if i < len(tokens) and tokens[i].lower() not in _KEYWORD_MAP:
                fields["scene"] = tokens[i]
                i += 1

        elif field == "take":
            if i < len(tokens) and _NUM.match(tokens[i]):
                start = int(tokens[i]); i += 1
                if (i + 1 < len(tokens)
                        and tokens[i].lower() == "through"
                        and _NUM.match(tokens[i + 1])):
                    fields["take"] = {"type": "numeric_range",
                                      "start": start, "end": int(tokens[i + 1])}
                    i += 2
                else:
                    fields["take"] = str(start)

        elif field == "camera":
            if i < len(tokens) and _LET.match(tokens[i]):
                start = tokens[i].upper(); i += 1
                if (i + 1 < len(tokens)
                        and tokens[i].lower() == "through"
                        and _LET.match(tokens[i + 1])):
                    fields["camera"] = {"type": "letter_range",
                                        "start": start, "end": tokens[i + 1].upper()}
                    i += 2
                else:
                    fields["camera"] = start

        else:
            # desc / loc / char / notes — multi-word until next keyword
            val: list[str] = []
            while i < len(tokens) and tokens[i].lower() not in _KEYWORD_MAP:
                val.append(tokens[i])
                i += 1
            if val:
                fields[field] = " ".join(val)

    if orphans and "description" not in fields:
        fields["description"] = " ".join(orphans)
        if "description" not in active:
            active.append("description")

    return fields, active


# ── Main parser ───────────────────────────────────────────────────────────────

class MetadataCommandParser:
    """
    Parses log-prefixed voice commands into ParseResult (rows + active columns).

    Grammar
    ───────
    log [scene X] [takes N through M | take N] [cam A through B | cam A] [text]
    log base [field value ...]       — store sticky fields
    log only [field value]           — single field override, keep rest from sticky
    log config <name>                — switch shot/format config file
    log profile <name>               — switch column profile (basic | full)

    Matrix rule: takes = outer loop, cams = inner loop.
    Trailing unmatched text auto-detected as shot type + description from config.
    ParseResult.columns = only these columns will be written to Premiere.
    """

    def __init__(self, config_name: str = DEFAULT_CONFIG):
        self.store = MetadataStore()
        if config_name != DEFAULT_CONFIG:
            self.store.set_config(config_name)

    # ── Public ────────────────────────────────────────────────────────────

    def parse(self, raw: str) -> ParseResult | None:
        """Returns ParseResult or None for control commands (base/config/profile)."""
        text  = raw.strip()
        lower = text.lower()

        if lower.startswith("log "):
            text  = text[4:].strip()
            lower = lower[4:].strip()
        elif lower == "log":
            return None

        # Config switch
        if m := re.match(r"config\s+(\S+)", lower):
            ok = self.store.set_config(m.group(1))
            print(f"[Config] {'-> ' + m.group(1) if ok else 'not found: ' + m.group(1)}")
            return None

        # Profile switch
        if m := re.match(r"profile\s+(\w+)", lower):
            self.store.set_profile(m.group(1))
            print(f"[Profile] -> {m.group(1)}")
            return None

        # Base set
        if lower.startswith("base "):
            fields, _ = _tokenize(text[5:].strip())
            clean = {k: v for k, v in fields.items() if isinstance(v, str)}
            self.store.set_base(clean)
            print(f"[Base] {clean}")
            return None

        # Only mode
        only_mode = False
        if lower.startswith("only "):
            only_mode = True
            text = text[5:].strip()

        fields, active_columns = _tokenize(text)
        rows = self._expand(fields, only_mode)
        return ParseResult(rows=rows, columns=active_columns)

    # ── Row generation ────────────────────────────────────────────────────

    def _expand(self, fields: dict, only_mode: bool) -> list[MetadataRow]:
        take_v = fields.get("take")
        cam_v  = fields.get("camera")

        takes = (_numeric_range(take_v["start"], take_v["end"])
                 if isinstance(take_v, dict) else
                 [take_v] if isinstance(take_v, str) else None)

        cams  = (_letter_range(cam_v["start"], cam_v["end"])
                 if isinstance(cam_v, dict) else
                 [cam_v] if isinstance(cam_v, str) else None)

        raw_desc = fields.get("description", "")
        desc = format_description(raw_desc, self.store.config) if raw_desc else ""

        static: dict[str, str] = {}
        if "scene" in fields:
            static["scene"] = fields["scene"]
        if desc:
            static["description"] = desc
        for f in ("location", "character", "notes"):
            if f in fields:
                static[f] = fields[f]

        rows: list[MetadataRow] = []

        if takes and cams:
            for take in takes:
                for cam in cams:
                    rows.append(self._row(
                        {**static, "take": take, "camera": f"{cam} Cam"}, only_mode))
        elif takes:
            for take in takes:
                rows.append(self._row({**static, "take": take}, only_mode))
        elif cams:
            for cam in cams:
                rows.append(self._row({**static, "camera": f"{cam} Cam"}, only_mode))
        elif static:
            rows.append(self._row(static, only_mode))

        return rows

    def _row(self, overrides: dict[str, str], only_mode: bool) -> MetadataRow:
        if only_mode:
            row = self.store.build_row()
            for k, v in overrides.items():
                setattr(row, k, v)
            return row
        return self.store.build_row(overrides)

    # ── Display ───────────────────────────────────────────────────────────

    def format_result(self, result: ParseResult | None) -> str:
        if result is None:
            return "  (control command — no rows)"
        if not result.rows:
            return "  (no rows generated)"
        cols = self.store.get_columns()
        lines = [f"  Writing to: {result.columns}"]
        for i, row in enumerate(result.rows, 1):
            parts = [
                f"{'*' if c in result.columns else ' '}{c.capitalize()}: {getattr(row, c) or '—'}"
                for c in cols
            ]
            lines.append(f"  Row {i:>2}: {' | '.join(parts)}")
        return "\n".join(lines)
