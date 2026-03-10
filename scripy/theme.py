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

# Supported code themes for rich Syntax highlighting
SUPPORTED_THEMES = [
    "default",
    "monokai",
    "emacs",
    "friendly",
    "fruity",
    "manni",
    "material",
    "murphy",
    "native",
    "one-dark",
    "paraiso",
    "pastie",
    "perldoc",
    "punk",
    "sas",
    "stata",
    "stata-light",
    "tango",
    "trac",
    "vim",
    "vs",
    "xcode",
    "autumn",
    "borland",
    "bw",
]


def get_code_theme(theme_name: str | None = None) -> str:
    """Get code theme, validating against supported themes."""
    if theme_name is None:
        return "dracula"
    if theme_name in SUPPORTED_THEMES or theme_name == "dracula":
        return theme_name
    return "default"
