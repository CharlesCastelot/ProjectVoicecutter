"""
Dry-run verification for the full parser + writer pipeline.

Uses a fake calibration so this runs without Premiere open.
Prints exactly what would be clicked and typed in real use.

Run: python test_writer.py
"""

from metadata_parser import MetadataCommandParser
from premiere_writer import write_metadata

# Fake calibration — mirrors a typical Premiere layout
FAKE_CALIBRATION = {
    "columns": {
        "scene":       312,
        "take":        445,
        "camera":      578,
        "description": 720,
        "location":    870,
        "character":   1010,
        "notes":       1150,
    },
    "row_height":          25,
    "first_row_y":         480,
    "selection_color":     [45, 90, 145],
    "selection_tolerance": 30,
}

STARTING_ROW_Y = 480  # simulate first clip at y=480

TESTS = [
    # ── Core workflows ────────────────────────────────────────────────────
    ("log scene 4A takes 1 through 5",
     "Takes only — scene + take columns, cam untouched"),

    ("log scene 4A cam A through D",
     "Cams only — scene + cam columns, take untouched"),

    ("log scene 4A takes 1 through 5 cam A through B",
     "Matrix 5x2 — all three columns, takes outer/cams inner"),

    ("log scene 4A take 1 cam A through D",
     "Single take, 4 cams"),

    # ── With description ──────────────────────────────────────────────────
    ("log scene 4A takes 1 through 3 wide John unclogs toilet",
     "Takes + description (shot type auto-detected)"),

    ("log scene 4A takes 1 through 3 cam A through B close up Mary argues",
     "Matrix + description"),

    # ── Control commands (no rows) ────────────────────────────────────────
    ("log base scene 7C",
     "Base set — no rows written"),

    ("log profile full",
     "Profile switch — no rows written"),
]


def run():
    print("=" * 72)
    print("  UI WRITER DRY-RUN VERIFICATION")
    print("  (fake calibration, no Premiere required)")
    print("=" * 72)

    parser = MetadataCommandParser()

    for cmd, label in TESTS:
        print(f"\n{'-' * 60}")
        print(f"  {label}")
        print(f"  CMD: {cmd!r}")
        print()

        result = parser.parse(cmd)

        if result is None:
            print("  (control command — nothing written)")
            continue

        write_metadata(
            result,
            FAKE_CALIBRATION,
            starting_row_y=STARTING_ROW_Y,
            dry_run=True,
        )

    print()
    print("=" * 72)
    print("  Dry run complete — no clicks were made.")
    print("=" * 72)


if __name__ == "__main__":
    run()
