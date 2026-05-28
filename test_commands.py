"""
Command format verification for the metadata parser.
Run: python test_commands.py
"""

from metadata_parser import MetadataCommandParser

TESTS = [
    # ── Profile & config ──────────────────────────────────────────────────
    ("log profile basic",
     "Switch to basic profile"),

    # ── Base / sticky ─────────────────────────────────────────────────────
    ("log base scene 4A",
     "Store sticky scene only"),

    # ── Takes only (no cam specified — don't touch cam column) ────────────
    ("log takes 1 through 5",
     "Takes 1–5, inherits sticky scene, cam column untouched"),

    ("log scene 4A takes 1 through 5",
     "Takes 1–5, explicit scene"),

    # ── Cam only ─────────────────────────────────────────────────────────
    ("log scene 4A cam A through D",
     "Cams A–D, take column untouched"),

    ("log cam A through B",
     "Cams A–B, inherits sticky scene"),

    # ── Matrix: takes × cams ─────────────────────────────────────────────
    ("log scene 4A takes 1 through 5 cam A through B",
     "Matrix 5 takes × 2 cams = 10 rows (takes outer, cams inner)"),

    ("log scene 4A takes 1 through 3 cam A through D",
     "Matrix 3 takes × 4 cams = 12 rows"),

    # ── Single take, multi-cam ────────────────────────────────────────────
    ("log scene 4A take 1 cam A through D",
     "Single take, 4 cameras = 4 rows"),

    # ── Single values ─────────────────────────────────────────────────────
    ("log scene 4A take 1 cam B",
     "Single row, all explicit"),

    # ── Description (trailing text, no keyword) ───────────────────────────
    ("log scene 4A takes 1 through 5 wide John unclogs toilet",
     "Takes with shot type + description"),

    ("log scene 4A takes 1 through 5 cam A through B close up Mary argues",
     "Matrix with shot type + description"),

    ("log scene 4A take 1 cam B over the shoulder John listens",
     "Single row, multi-word shot type"),

    ("log scene 4A take 1 cam B John unclogs toilet",
     "Description with no shot type (no match in config)"),

    # ── desc keyword ──────────────────────────────────────────────────────
    ("log scene 4A take 1 cam B desc wide John unclogs toilet",
     "Explicit desc keyword with shot type"),

    # ── Only mode ─────────────────────────────────────────────────────────
    ("log only take 3",
     "Only mode: change take, keep sticky"),

    ("log only cam C",
     "Only mode: change cam, keep sticky"),

    # ── Full profile ──────────────────────────────────────────────────────
    ("log profile full",
     "Switch to full profile"),

    ("log base scene 7C loc kitchen char Maya notes argument beat",
     "Set full sticky base"),

    ("log takes 1 through 3 wide Maya slams door",
     "Takes with full sticky + shot type desc, full profile"),

    # ── Config switch ─────────────────────────────────────────────────────
    ("log config example_posthaus",
     "Switch to alternate post house config"),

    ("log scene 5B take 2 cam A wide John enters",
     "Same command, different config — abbreviations + uppercase + dash separator"),

    ("log config default",
     "Switch back to default config"),
]


def run():
    print("=" * 72)
    print("  METADATA COMMAND FORMAT VERIFICATION")
    print("=" * 72)

    parser = MetadataCommandParser()

    for cmd, label in TESTS:
        print(f"\n[{label}]")
        print(f"  CMD : {cmd!r}")
        result = parser.parse(cmd)
        print(parser.format_result(result))
        if result:
            print(f"  Sticky: {parser.store._fields or '(empty)'} | "
                  f"Profile: {parser.store.profile} | "
                  f"Config: {parser.store.config_name}")

    print("\n" + "=" * 72)
    print("  Done.")
    print("=" * 72)


if __name__ == "__main__":
    run()
