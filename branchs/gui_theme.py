"""Color palettes shared by the GUI's Tk and ttk widgets."""

PALETTES = {
    "light": {
        "window": "#edf0f4", "surface": "#f8f9fb", "header": "#e5eaf0",
        "input": "#ffffff", "tree": "#f8f9fb", "heading": "#e8edf3",
        "text": "#202938", "muted": "#526174", "border": "#cbd4df",
        "button": "#eef2f6", "button_hover": "#dde6ef", "button_text": "#253247",
        "accent": "#3157a4", "accent_hover": "#254582", "accent_text": "#ffffff",
        "selected": "#dce7f6", "selected_text": "#183c7a",
        "added": "#126c3a", "deleted": "#a32d36", "modified": "#2855a2",
    },
    "dark": {
        "window": "#151b24", "surface": "#1d2632", "header": "#19212c",
        "input": "#253140", "tree": "#202b38", "heading": "#2b3949",
        "text": "#e9eef6", "muted": "#b3c0cf", "border": "#405064",
        "button": "#2b394a", "button_hover": "#3a4b5f", "button_text": "#edf2fa",
        "accent": "#87acef", "accent_hover": "#a3c2f7", "accent_text": "#132235",
        "selected": "#35527a", "selected_text": "#f3f7ff",
        "added": "#9de2b4", "deleted": "#ffafb0", "modified": "#b7d0ff",
    },
}


def palette(theme: str) -> dict:
    return PALETTES.get(theme, PALETTES["light"])
