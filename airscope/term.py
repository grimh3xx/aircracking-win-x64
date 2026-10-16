"""Camada de terminal: raw mode, teclas com timeout, tela alternativa, desenho sem flicker.

Multiplataforma: POSIX (termios) e Windows (msvcrt + VT via SetConsoleMode).
No Windows so o modo --demo faz sentido (a auditoria real e Linux), mas a UI roda.
"""
import os
import shutil
import sys
import time

_WIN = os.name == "nt"

if _WIN:
    import ctypes
    import msvcrt
else:
    import select
    import termios
    import tty

# Teclas especiais
UP, DOWN, LEFT, RIGHT = "UP", "DOWN", "LEFT", "RIGHT"
PGUP, PGDN, HOME, END = "PGUP", "PGDN", "HOME", "END"
ENTER, ESCAPE, BACKSPACE, TAB, SPACE = "ENTER", "ESCAPE", "BACKSPACE", "TAB", "SPACE"
RESIZE, NONE = "RESIZE", "NONE"


def _enable_windows_vt():
    """Liga ENABLE_VIRTUAL_TERMINAL_PROCESSING no stdout do Windows (cores ANSI)."""
    try:
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)
        return True
    except Exception:
        return False


class Terminal:
    def __init__(self):
        self._old = None
        self._active = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ---- ciclo de vida ----
    def start(self):
        if _WIN:
            _enable_windows_vt()
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
            self._active = True
            self._write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
            return
        if not sys.stdin.isatty():
            self._active = True
            return
        self._old = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())
        self._active = True
        self._write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._write("\x1b[0m\x1b[?25h\x1b[?1049l")
        if not _WIN and self._old is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)

    # ---- dimensoes ----
    @property
    def size(self):
        s = shutil.get_terminal_size((100, 30))
        return s.columns, s.lines

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    # ---- saida ----
    def _write(self, s):
        try:
            if _WIN:
                sys.stdout.write(s)
                sys.stdout.flush()
            else:
                os.write(sys.stdout.fileno(), s.encode("utf-8", "replace"))
        except OSError:
            pass

    def present(self, lines):
        h = self.height
        out = ["\x1b[H"]
        n = 0
        for ln in lines:
            if n >= h:
                break
            out.append(ln)
            out.append("\x1b[0m\x1b[K")
            n += 1
            if n < h:
                out.append("\r\n")
        out.append("\x1b[J")
        self._write("".join(out))

    # ---- entrada ----
    def read_key(self, timeout=None):
        if _WIN:
            return self._read_key_win(timeout)
        return self._read_key_posix(timeout)

    # ----- Windows -----
    def _read_key_win(self, timeout):
        end = (time.time() + timeout) if timeout is not None else None
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):  # prefixo de tecla especial
                    ch2 = msvcrt.getwch()
                    table = {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT,
                             "I": PGUP, "Q": PGDN, "G": HOME, "O": END}
                    return (table.get(ch2, NONE), "")
                if ch in ("\r", "\n"):
                    return (ENTER, "")
                if ch == "\x1b":
                    return (ESCAPE, "")
                if ch in ("\x08", "\x7f"):
                    return (BACKSPACE, "")
                if ch == "\t":
                    return (TAB, "")
                if ch == " ":
                    return (SPACE, " ")
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch >= " ":
                    return ("CHAR", ch)
                return (NONE, "")
            if end is not None and time.time() >= end:
                return (NONE, "")
            time.sleep(0.01)

    # ----- POSIX -----
    def _read_key_posix(self, timeout):
        if not sys.stdin.isatty():
            return (NONE, "")
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            return (NONE, "")
        ch = os.read(sys.stdin.fileno(), 1)
        if not ch:
            return (NONE, "")
        b = ch[0]
        if b == 0x1b:
            return self._read_escape_posix()
        if b in (0x0d, 0x0a):
            return (ENTER, "")
        if b in (0x7f, 0x08):
            return (BACKSPACE, "")
        if b == 0x09:
            return (TAB, "")
        if b == 0x20:
            return (SPACE, " ")
        if b == 0x03:
            raise KeyboardInterrupt
        if b < 0x20:
            return (NONE, "")
        extra = 3 if b >= 0xF0 else 2 if b >= 0xE0 else 1 if b >= 0xC0 else 0
        data = ch + (os.read(sys.stdin.fileno(), extra) if extra else b"")
        try:
            return ("CHAR", data.decode("utf-8"))
        except UnicodeDecodeError:
            return (NONE, "")

    def _read_escape_posix(self):
        r, _, _ = select.select([sys.stdin], [], [], 0.02)
        if not r:
            return (ESCAPE, "")
        b2 = os.read(sys.stdin.fileno(), 1)
        if b2 not in (b"[", b"O"):
            return (ESCAPE, "")
        seq = b""
        for _ in range(6):
            r, _, _ = select.select([sys.stdin], [], [], 0.02)
            if not r:
                break
            c = os.read(sys.stdin.fileno(), 1)
            seq += c
            if c.isalpha() or c == b"~":
                break
        s = seq.decode("latin1")
        table = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END,
                 "5~": PGUP, "6~": PGDN, "1~": HOME, "4~": END, "7~": HOME, "8~": END}
        return (table.get(s, NONE), "")

    def set_title(self, title):
        self._write(f"\x1b]0;{title}\x07")


def supports_truecolor():
    return True
