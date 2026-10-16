"""Logo CentralTech em pixel-art (meio-blocos ▀▄ + cor 24-bit) e barras de cabecalho."""
from . import textutil as T
from . import theme as TH
from . import logo_data as L

HEADER_ROWS = 5


def _pixel(x, y):
    if y < 0 or y >= L.H or x < 0:
        return -1
    row = L.ROWS[y]
    if x >= len(row):
        return -1
    idx = row[x]
    return -1 if idx < 0 else L.PALETTE[idx]


def _render_rows(y0, y1, left_pad):
    """Converte linhas de pixel [y0,y1) em linhas de terminal (2 px por linha)."""
    out = []
    for y in range(y0, y1, 2):
        line = [" " * left_pad]
        cur_fg = cur_bg = None
        pending = 0
        for x in range(L.W):
            top = _pixel(x, y)
            bot = _pixel(x, y + 1) if (y + 1) < y1 else -1
            if top < 0 and bot < 0:
                pending += 1
                continue
            if pending:
                if cur_bg is not None:
                    line.append("\x1b[49m")
                    cur_bg = None
                line.append(" " * pending)
                pending = 0
            if top >= 0 and bot >= 0:
                if top == bot:
                    glyph, want_fg, want_bg = "█", top, None
                else:
                    glyph, want_fg, want_bg = "▀", top, bot
            elif top >= 0:
                glyph, want_fg, want_bg = "▀", top, None
            else:
                glyph, want_fg, want_bg = "▄", bot, None
            if want_fg != cur_fg:
                line.append(T.fg(want_fg))
                cur_fg = want_fg
            if want_bg is not None and want_bg != cur_bg:
                line.append(T.bg(want_bg))
                cur_bg = want_bg
            elif want_bg is None and cur_bg is not None:
                line.append("\x1b[49m")
                cur_bg = None
            line.append(glyph)
        line.append(T.RESET)
        out.append("".join(line))
    return out


def _pad_for(term_w, content_w):
    return (term_w - content_w) // 2 if term_w > content_w else 0


def _header(left_pad, links_on):
    pad = " " * left_pad
    out = []
    # "S O L U T I O N S"
    sol = [" "] * L.W
    for i, ch in enumerate("SOLUTIONS"):
        col = L.SOLUTIONS_COL + i * 6
        if col < len(sol):
            sol[col] = ch
    sol_s = "".join(sol).rstrip()
    out.append(pad + T.fg(TH.ACCENT) + sol_s + T.RESET)

    rule = T.gradient(T.repeat("─", L.W), TH.BLUE, TH.CYAN)
    out.append(pad + rule)

    title = (T.BOLD + T.fg(TH.WHITE) + TH.APP_TITLE + T.RESET +
             T.fg(TH.DIM) + "  ·  " + TH.VERSION + T.RESET)
    out.append(pad + T.center(title, L.W))

    def lnk(host, url):
        return (T.fg(TH.CYAN) + "► " + T.fg(TH.TEXT) + T.UNDERLINE +
                T.link(url, host, links_on) + T.NO_UNDERLINE + T.RESET)

    links = (lnk(TH.SITE, "https://" + TH.SITE) + "        " +
             lnk(TH.GITHUB, "https://" + TH.GITHUB))
    out.append(pad + T.center(links, L.W))
    out.append(pad + rule)
    return out


def rows_for(tier):
    if tier == "full":
        return (L.H + 1) // 2 + HEADER_ROWS
    if tier == "word":
        return (L.H - L.WORD_START + 1) // 2 + HEADER_ROWS
    return 3


def best_tier(term_w, max_rows):
    if term_w < L.W:
        return "text"
    if max_rows >= rows_for("full"):
        return "full"
    if max_rows >= rows_for("word"):
        return "word"
    return "text"


def build(term_w, tier, links_on=False):
    out = []
    if tier == "text":
        brand = (T.BOLD + T.fg(TH.WHITE) + "Central" + T.fg(TH.CYAN) + "Tech" + T.RESET +
                 T.fg(TH.ACCENT) + "  SOLUTIONS" + T.RESET)
        sub = (T.fg(TH.TEXT) + TH.APP_TITLE + T.fg(TH.DIM) + "  ·  " + TH.VERSION +
               "  ·  " + TH.SITE + T.RESET)
        out.append(T.center(brand, term_w))
        out.append(T.center(sub, term_w))
        w = term_w - 4 if term_w > 4 else term_w
        out.append("  " + T.gradient(T.repeat("─", w), TH.BLUE, TH.CYAN))
        return out
    pad = _pad_for(term_w, L.W)
    out.extend(_render_rows(0 if tier == "full" else L.WORD_START, L.H, pad))
    out.extend(_header(pad, links_on))
    return out


def top_bar(term_w, section):
    left = (T.fg(TH.BLUE) + "▌" + T.BOLD + T.fg(TH.WHITE) + "Central" + T.fg(TH.CYAN) + "Tech" +
            T.RESET + T.fg(TH.DIM) + "  " + TH.APP_TITLE + T.RESET)
    if section:
        left += T.fg(TH.DIM) + "  ›  " + T.RESET + T.BOLD + section + T.RESET
    right = T.fg(TH.DIM) + TH.VERSION + T.RESET
    total = term_w - 1 if term_w > 1 else 1
    lw, rw = T.width(left), T.width(right)
    line = left
    if lw + rw + 1 < total:
        line += " " * (total - lw - rw) + right
    return [line, T.gradient(T.repeat("─", total), TH.BLUE, TH.CYAN)]
