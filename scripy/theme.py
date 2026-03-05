from rich import box

# Glyphs
WORKING = "▸"
SUCCESS = "✓"
FAILED = "✗"
WARNING = "~"
PROMPT = "?"

# Colors
AMBER = "#F59E0B"
MUTED = "#64748B"
SUCCESS_COLOR = "#4ADE80"
ERROR_COLOR = "#F87171"
WARNING_COLOR = "#FBF724"
CODE_THEME = "dracula"

# Box style
BOX = box.MINIMAL

# Spinner frames
SPINNER_FRAMES = ["⚬⚬⚬⚬", "•⚬⚬⚬", "••⚬⚬", "⚬••⚬", "⚬⚬••", "⚬⚬⚬•", "⚬⚬⚬⚬"]

# Supported languages: (display label, lang id)  — None id = "other" / free text
LANGUAGES: list[tuple[str, str | None]] = [
    ("python", "python"),
    ("bash", "bash"),
    ("ruby", "ruby"),
    ("javascript", "javascript"),
    ("other", None),
]
