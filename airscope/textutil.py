"""Utilitarios de texto: cor ANSI 24-bit, largura visivel, ajuste, degrade."""
import re

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
UNDERLINE = "\x1b[4m"
NO_UNDERLINE = "\x1b[24m"

_ANSI = re.compile(r"\x1b\[[0-9;]*m|\x1b\]8;;[^\x1b\x07]*(?:\x07|\x1b\\)")


def fg(rgb):
    return f"\x1b[38;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def bg(rgb):
    return f"\x1b[48;2;{(rgb >> 16) & 255};{(rgb >> 8) & 255};{rgb & 255}m"


def strip(s):
    return _ANSI.sub("", s)


def width(s):
    """Largura visivel: ignora escapes ANSI e conta code points."""
    return len(strip(s))


def fit(s, w):
    """Corta com reticencias ou completa com espacos ate largura w (conta visivel)."""
    vis = width(s)
    if vis <= w:
        return s + " " * (w - vis)
    if w <= 0:
        return ""
    out = []
    count = 0
    i = 0
    had_ansi = False
    while i < len(s):
        m = _ANSI.match(s, i)
        if m:
            out.append(m.group())
            had_ansi = True
            i = m.end()
            continue
        if count >= w - 1:
            break
        out.append(s[i])
        count += 1
        i += 1
    out.append("…")
    if had_ansi:
        out.append(RESET)
    return "".join(out)


def pad_left(s, w):
    vis = width(s)
    return (" " * (w - vis) + s) if vis < w else s


def center(s, w):
    vis = width(s)
    return (" " * ((w - vis) // 2) + s) if vis < w else s


def repeat(unit, n):
    return unit * max(0, n)


def link(url, text, enabled=True):
    if not enabled:
        return text
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def gradient(s, c_from, c_to):
    """Degrade horizontal de c_from a c_to ao longo dos caracteres visiveis."""
    chars = [c for c in s]
    n = len(chars)
    out = []
    for i, ch in enumerate(chars):
        t = i / (n - 1) if n > 1 else 0.0
        r = round(((c_from >> 16) & 255) + (((c_to >> 16) & 255) - ((c_from >> 16) & 255)) * t)
        g = round(((c_from >> 8) & 255) + (((c_to >> 8) & 255) - ((c_from >> 8) & 255)) * t)
        b = round((c_from & 255) + ((c_to & 255) - (c_from & 255)) * t)
        out.append(fg((r << 16) | (g << 8) | b) + ch)
    out.append(RESET)
    return "".join(out)


def bar(frac, w, fill_color, empty_color):
    """Barra de progresso de largura w; frac em [0,1]."""
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * w)
    return fg(fill_color) + "█" * filled + fg(empty_color) + "░" * (w - filled) + RESET
