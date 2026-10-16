"""airscope — orquestrador de auditoria Wi-Fi em TUI. (c) CentralTech Solutions.

Uso autorizado apenas: so teste redes que voce possui ou tem permissao explicita
por escrito pra auditar.
"""
from __future__ import annotations

import threading
import time

from . import banner
from . import term as TM
from . import textutil as T
from . import theme as TH
from .backend.base import power_bars


def _sig_bars(power):
    n = power_bars(power)
    full = "▁▃▅▇"
    cells = []
    for i in range(4):
        c = full[i]
        cells.append((T.fg(TH.GREEN if n >= 3 else TH.YELLOW if n >= 1 else TH.DIM) if i < n
                      else T.fg(TH.FAINT)) + c)
    return "".join(cells) + T.RESET


def _enc_color(enc):
    return {"OPN": TH.RED, "WEP": TH.ORANGE, "WPA": TH.YELLOW,
            "WPA2": TH.GREEN, "WPA3": TH.CYAN}.get(enc, TH.TEXT)


class App:
    def __init__(self, backend, default_wordlist="/usr/share/wordlists/rockyou.txt"):
        self.b = backend
        self.term = TM.Terminal()
        self.screen = "interfaces"
        self.running = True
        self.status = "demo mode — dados simulados" if backend.demo else "pronto"
        self.links_on = True

        self.interfaces = []
        self.iface = None
        self.sel_if = 0

        self.networks = []
        self.net_lock = threading.Lock()
        self.sel_net = 0
        self.net_top = 0
        self.scan_stop = None
        self.scan_thread = None

        self.target = None
        self.capture = None
        self.cap_stop = None
        self.cap_thread = None

        self.wordlist = default_wordlist
        self.wl_input = default_wordlist
        self.crack = None
        self.crack_stop = None
        self.crack_thread = None

        self.toast = ""
        self.toast_until = 0.0

    # ---------------- ciclo ----------------
    def run(self):
        with self.term:
            self.term.set_title("CentralTech · airscope")
            self.interfaces = self.b.list_interfaces()
            self._loop()
        self._stop_all_threads()

    def _say(self, msg, secs=3.0):
        self.toast = msg
        self.toast_until = time.time() + secs

    def _loop(self):
        while self.running:
            self._draw()
            # telas com atualizacao ao vivo redesenham mais rapido
            live = self.screen in ("scan", "capture", "crack")
            key = self.term.read_key(timeout=0.25 if live else None)
            k, ch = key
            if k == TM.RESIZE or k == TM.NONE:
                continue
            handler = getattr(self, f"_key_{self.screen}", None)
            if handler:
                handler(k, ch)

    def _stop_all_threads(self):
        for ev in (self.scan_stop, self.cap_stop, self.crack_stop):
            if ev:
                ev.set()

    # ---------------- helpers de desenho ----------------
    def _frame(self, section, body_lines, keys):
        w, h = self.term.size
        out = banner.top_bar(w, section)
        out.append("")
        avail = h - len(out) - 2
        for i in range(avail):
            out.append("  " + body_lines[i] if i < len(body_lines) else "")
        self._footer(out, keys, w, h)
        return out

    def _footer(self, out, keys, w, h):
        # reserva as 2 ultimas linhas pro rodape (regua + teclas/status)
        del out[h - 2:]
        while len(out) < h - 2:
            out.append("")
        status = self.status
        if self.toast and time.time() < self.toast_until:
            status = self.toast
        left = T.fg(TH.DIM) + keys + T.RESET
        right = T.fg(TH.DIM) + status + T.RESET
        lw, rw = T.width(left), T.width(right)
        line = " " + left
        if lw + rw + 3 < w:
            line += " " * (w - lw - rw - 3) + right + " "
        out.append(T.gradient(T.repeat("─", max(1, w)), TH.FAINT, TH.FAINT))
        out.append(line)

    def _draw(self):
        drawer = getattr(self, f"_draw_{self.screen}", None)
        self.term.present(drawer() if drawer else ["?"])

    # ======================================================
    # TELA: interfaces
    # ======================================================
    def _draw_interfaces(self):
        w, h = self.term.size
        out = []
        tier = banner.best_tier(w, h - 8)
        out.extend(banner.build(w, tier, self.links_on))
        out.append("")
        body = []
        body.append(T.BOLD + T.fg(TH.CYAN) + "Interfaces wireless" + T.RESET)
        body.append("")
        if not self.interfaces:
            body.append(T.fg(TH.RED) + "  Nenhuma interface wireless encontrada." + T.RESET)
            body.append(T.fg(TH.DIM) + "  Conecte um adaptador que suporte monitor mode." + T.RESET)
        for i, it in enumerate(self.interfaces):
            sel = i == self.sel_if
            mark = T.fg(TH.CYAN) + "▌ " + T.RESET if sel else "  "
            name = (T.BOLD if sel else "") + T.fg(TH.WHITE) + T.fit(it.name, 10) + T.RESET
            mon = (T.fg(TH.GREEN) + "● monitor" if it.monitor else T.fg(TH.DIM) + "○ managed") + T.RESET
            info = T.fg(TH.TEXT) + (it.chipset or it.driver or "") + T.RESET
            body.append(mark + name + "  " + T.fit(mon, 18) + "  " + info)
        for ln in self._compose(out, body, h):
            out.append(ln)
        self._footer(out, "↑↓ escolher   ↵ usar (ativa monitor)   q sair", w, h)
        return out

    def _compose(self, header, body, h):
        avail = h - len(header) - 2
        return ["  " + body[i] if i < len(body) else "" for i in range(avail)]

    def _key_interfaces(self, k, ch):
        if k == TM.UP:
            self.sel_if = max(0, self.sel_if - 1)
        elif k == TM.DOWN:
            self.sel_if = min(len(self.interfaces) - 1, self.sel_if + 1) if self.interfaces else 0
        elif k == TM.ENTER and self.interfaces:
            self.iface = self.interfaces[self.sel_if]
            self._start_scan()
        elif k == "CHAR" and ch == "q" or k == TM.ESCAPE:
            self.running = False

    # ======================================================
    # TELA: scan
    # ======================================================
    def _start_scan(self):
        if not self.iface.monitor:
            self.status = f"ativando monitor mode em {self.iface.name}…"
            self._draw()
            self.iface = self.b.enable_monitor(self.iface)
            self._say(f"monitor mode on: {self.iface.mon_name}", 3)
        self.screen = "scan"
        self.sel_net = 0
        self.net_top = 0
        self.scan_stop = threading.Event()

        def worker():
            def on_update(nets):
                nets.sort(key=lambda n: n.power, reverse=True)
                with self.net_lock:
                    self.networks = nets
            self.b.scan(self.iface, on_update, self.scan_stop)
        self.scan_thread = threading.Thread(target=worker, daemon=True)
        self.scan_thread.start()

    def _scan_rows_avail(self, h):
        return max(1, h - 2 - (2 + 2))  # topbar(2)+blank..., header tabela(2), rodape(2)

    def _draw_scan(self):
        w, h = self.term.size
        with self.net_lock:
            nets = list(self.networks)
        out = banner.top_bar(w, f"Scan · {self.iface.mon_name or self.iface.name}")
        out.append("")
        # cabecalho da tabela
        cols = self._net_cols(w)
        out.append("  " + self._net_header(cols))
        rows = h - len(out) - 2
        if self.sel_net >= len(nets):
            self.sel_net = max(0, len(nets) - 1)
        if self.sel_net < self.net_top:
            self.net_top = self.sel_net
        if self.sel_net >= self.net_top + rows:
            self.net_top = self.sel_net - rows + 1
        if not nets:
            out.append("")
            out.append("  " + T.fg(TH.DIM) + "  escaneando… " + _spinner() + T.RESET)
        for i in range(rows):
            idx = self.net_top + i
            if idx >= len(nets):
                out.append("")
                continue
            out.append("  " + self._net_row(nets[idx], cols, idx == self.sel_net))
        n_crack = sum(1 for n in nets if n.crackable)
        self.status = f"{len(nets)} redes · {n_crack} com WPA/WPA2-PSK"
        keys = "↑↓ mover   ↵ capturar handshake   r re-scan   esc interfaces   q sair"
        self._footer(out, keys, w, h)
        return out

    class _Cols:
        pass

    def _net_cols(self, w):
        c = App._Cols()
        c.sel, c.sig, c.pwr, c.ch, c.enc, c.cli, c.bssid = 2, 7, 6, 4, 6, 4, 19
        rest = w - (c.sel + c.sig + c.pwr + c.ch + c.enc + c.cli + c.bssid) - 6
        c.essid = max(12, rest)
        return c

    def _net_header(self, c):
        cell = lambda s, wi: T.fit(s, max(0, wi))
        return (T.fg(TH.DIM) + " " * c.sel + cell("sinal", c.sig) + cell("dBm", c.pwr) +
                cell("ch", c.ch) + cell("enc", c.enc) + cell("cli", c.cli) +
                cell("ESSID", c.essid) + cell("BSSID", c.bssid) + T.RESET)

    def _net_row(self, n, c, selected):
        cell = lambda s, wi: T.fit(s, max(0, wi))
        reset = T.bg(TH.SEL_BG) if selected else T.RESET
        mark = (T.fg(TH.CYAN) + "▌" + T.RESET + T.bg(TH.SEL_BG) + " ") if selected else "  "
        essid = n.essid if n.essid else "<oculta>"
        name_c = TH.WHITE if n.crackable else TH.DIM
        lock = ""
        if not n.crackable and n.enc in ("WPA3",):
            lock = T.fg(TH.DIM) + " ⃰" + T.RESET
        line = (mark + _sig_bars(n.power) + reset + " " +
                T.fg(TH.TEXT) + cell(str(n.power), c.pwr) +
                T.fg(TH.TEXT) + cell(str(n.channel), c.ch) +
                T.fg(_enc_color(n.enc)) + cell(n.enc, c.enc) +
                T.fg(TH.DIM) + cell(str(n.clients or ""), c.cli) +
                (T.BOLD if selected else "") + T.fg(name_c) + cell(essid, c.essid) +
                ("\x1b[22m" if selected else "") +
                T.fg(TH.DIM) + cell(n.bssid, c.bssid))
        return line + T.RESET

    def _key_scan(self, k, ch):
        with self.net_lock:
            n = len(self.networks)
        if k == TM.UP:
            self.sel_net = max(0, self.sel_net - 1)
        elif k == TM.DOWN:
            self.sel_net = min(n - 1, self.sel_net + 1) if n else 0
        elif k == TM.HOME:
            self.sel_net = 0
        elif k == TM.END and n:
            self.sel_net = n - 1
        elif k == TM.ENTER and n:
            with self.net_lock:
                net = self.networks[self.sel_net]
            if not net.crackable:
                self._say("rede sem WPA/WPA2-PSK: captura de handshake nao se aplica", 3.5)
                return
            self.target = net
            self.screen = "authorize"
        elif k == "CHAR" and ch == "r":
            with self.net_lock:
                self.networks = []
            self._say("re-escaneando…", 2)
        elif k == TM.ESCAPE:
            self._stop_scan()
            self.screen = "interfaces"
        elif k == "CHAR" and ch == "q":
            self.running = False

    def _stop_scan(self):
        if self.scan_stop:
            self.scan_stop.set()
        if self.scan_thread:
            self.scan_thread.join(timeout=2)

    # ======================================================
    # TELA: authorize (gate de consentimento)
    # ======================================================
    def _draw_authorize(self):
        w, h = self.term.size
        n = self.target
        body = []
        body.append(T.BOLD + T.fg(TH.YELLOW) + "⚠  Confirmacao de autorizacao" + T.RESET)
        body.append("")
        body.append(T.fg(TH.TEXT) + "Voce esta prestes a capturar o handshake de:" + T.RESET)
        body.append("")
        body.append("    " + T.BOLD + T.fg(TH.WHITE) + (n.essid or "<oculta>") + T.RESET +
                    T.fg(TH.DIM) + "   " + n.bssid + "   ch " + str(n.channel) + T.RESET)
        body.append("")
        for ln in T_wrap(
            "Isto envia pacotes de deauth e captura trafego da rede. So faca isto em redes "
            "que voce possui ou tem permissao EXPLICITA e por escrito pra auditar. Uso nao "
            "autorizado e crime na maioria dos paises (no Brasil, Lei 12.737; na Australia, "
            "Cybercrime Act 2001).", w - 8):
            body.append(T.fg(TH.DIM) + ln + T.RESET)
        body.append("")
        body.append(T.fg(TH.GREEN) + "  [s]" + T.fg(TH.TEXT) + " estou autorizado, continuar     " +
                    T.fg(TH.RED) + "[n]" + T.fg(TH.TEXT) + " cancelar" + T.RESET)
        out = self._frame("Autorizacao", body, "s confirmar   n/esc cancelar")
        return out

    def _key_authorize(self, k, ch):
        if k == "CHAR" and ch == "s":
            self._start_capture()
        elif (k == "CHAR" and ch == "n") or k == TM.ESCAPE:
            self.screen = "scan"

    # ======================================================
    # TELA: capture
    # ======================================================
    def _start_capture(self):
        self._stop_scan()
        self.screen = "capture"
        self.cap_stop = threading.Event()
        self.capture = None

        def worker():
            def on_update(st):
                self.capture = st
            self.b.capture(self.iface, self.target, on_update, self.cap_stop, deauth=True)
        self.cap_thread = threading.Thread(target=worker, daemon=True)
        self.cap_thread.start()

    def _draw_capture(self):
        w, h = self.term.size
        n = self.target
        st = self.capture
        body = []
        body.append(T.BOLD + T.fg(TH.WHITE) + (n.essid or "<oculta>") + T.RESET +
                    T.fg(TH.DIM) + "   " + n.bssid + "   ch " + str(n.channel) + T.RESET)
        body.append("")
        got = st and st.handshake
        if got:
            body.append(T.fg(TH.GREEN) + T.BOLD + "  ✔ HANDSHAKE CAPTURADO" + T.RESET)
        else:
            body.append(T.fg(TH.CYAN) + "  ⟳ capturando handshake " + _spinner() +
                        T.fg(TH.DIM) + "   (deauth pra forcar reconexao)" + T.RESET)
        body.append("")
        elapsed = int(st.elapsed) if st else 0
        deauths = st.deauths_sent if st else 0
        body.append("  " + T.fg(TH.DIM) + T.fit("tempo", 17) + T.RESET +
                    T.fg(TH.TEXT) + f"{elapsed}s" + T.RESET)
        body.append("  " + T.fg(TH.DIM) + T.fit("deauth enviados", 17) + T.RESET +
                    T.fg(TH.TEXT) + str(deauths) + T.RESET)
        clients = st.clients if st else []
        body.append("  " + T.fg(TH.DIM) + T.fit("clientes", 17) + T.RESET +
                    T.fg(TH.TEXT) + str(len(clients)) + T.RESET)
        for cl in clients[:6]:
            body.append("      " + T.fg(TH.DIM) + cl.mac + "   " + str(cl.power) + " dBm" + T.RESET)
        body.append("")
        if got:
            body.append(T.fg(TH.TEXT) + "  Handshake salvo em " + T.fg(TH.CYAN) +
                        (st.cap_path or "") + T.RESET)
            body.append("")
            body.append(T.fg(TH.GREEN) + "  [c]" + T.fg(TH.TEXT) + " partir pro crack offline" + T.RESET)
        keys = ("↵/c crack   esc parar e voltar" if got else "esc parar captura")
        return self._frame("Captura", body, keys)

    def _key_capture(self, k, ch):
        got = self.capture and self.capture.handshake
        if got and (k == TM.ENTER or (k == "CHAR" and ch == "c")):
            self.screen = "wordlist"
        elif k == TM.ESCAPE:
            if self.cap_stop:
                self.cap_stop.set()
            self.screen = "scan"
            self._start_scan()
        elif k == "CHAR" and ch == "q":
            self.running = False

    # ======================================================
    # TELA: wordlist (escolha do dicionario)
    # ======================================================
    def _draw_wordlist(self):
        w, h = self.term.size
        body = []
        body.append(T.BOLD + T.fg(TH.CYAN) + "Wordlist pro crack offline" + T.RESET)
        body.append("")
        body.append(T.fg(TH.TEXT) + "Caminho do dicionario:" + T.RESET)
        body.append("")
        box = T.fg(TH.CYAN) + "  ▸ " + T.RESET + T.fg(TH.WHITE) + self.wl_input + T.RESET + "▏"
        body.append(box)
        body.append("")
        import os
        exists = os.path.exists(self.wl_input)
        body.append(("  " + T.fg(TH.GREEN) + "✔ arquivo existe" if exists
                     else "  " + T.fg(TH.YELLOW) + "⚠ arquivo nao encontrado (confira o caminho)") + T.RESET)
        body.append("")
        body.append(T.fg(TH.DIM) + "  comuns: /usr/share/wordlists/rockyou.txt" + T.RESET)
        return self._frame("Wordlist", body, "digite o caminho   ↵ iniciar crack   esc voltar")

    def _key_wordlist(self, k, ch):
        if k == TM.ENTER:
            self.wordlist = self.wl_input.strip()
            if self.wordlist:
                self._start_crack()
        elif k == TM.ESCAPE:
            self.screen = "capture"
        elif k == TM.BACKSPACE:
            self.wl_input = self.wl_input[:-1]
        elif k == "CHAR":
            self.wl_input += ch
        elif k == TM.SPACE:
            self.wl_input += " "

    # ======================================================
    # TELA: crack
    # ======================================================
    def _start_crack(self):
        self.screen = "crack"
        self.crack_stop = threading.Event()
        self.crack = None

        def worker():
            def on_update(st):
                self.crack = st
            self.b.crack(self.capture, self.wordlist, on_update, self.crack_stop)
        self.crack_thread = threading.Thread(target=worker, daemon=True)
        self.crack_thread.start()

    def _draw_crack(self):
        w, h = self.term.size
        n = self.target
        st = self.crack
        body = []
        body.append(T.BOLD + T.fg(TH.WHITE) + (n.essid or "<oculta>") + T.RESET +
                    T.fg(TH.DIM) + "   " + n.bssid + T.RESET)
        body.append(T.fg(TH.DIM) + "  " + self.wordlist + T.RESET)
        body.append("")
        if st and st.found:
            body.append(T.fg(TH.GREEN) + T.BOLD + "  ✔ SENHA ENCONTRADA" + T.RESET)
            body.append("")
            body.append("    " + T.bg(TH.SEL_BG) + T.BOLD + T.fg(TH.GREEN) + "  " +
                        st.password + "  " + T.RESET)
        elif st and st.done:
            body.append(T.fg(TH.YELLOW) + T.BOLD + "  ✗ senha nao esta na wordlist" + T.RESET)
            body.append(T.fg(TH.DIM) + "  tente outro dicionario ou regras (hashcat -r)" + T.RESET)
        else:
            body.append(T.fg(TH.CYAN) + "  ⟳ testando senhas " + _spinner() + T.RESET)
        body.append("")
        frac = st.progress if st else 0.0
        barw = min(48, max(10, w - 24))
        body.append("  " + T.bar(frac, barw, TH.CYAN, TH.FAINT) + "  " +
                    T.fg(TH.WHITE) + f"{frac*100:5.1f}%" + T.RESET)
        body.append("")
        if st:
            body.append("  " + T.fg(TH.DIM) + T.fit("velocidade", 14) + T.RESET +
                        T.fg(TH.TEXT) + (st.speed or "—") + T.RESET)
            body.append("  " + T.fg(TH.DIM) + T.fit("testadas", 14) + T.RESET +
                        T.fg(TH.TEXT) + f"{st.tried:,} / {st.total:,}".replace(",", ".") + T.RESET)
            if not st.done and st.eta:
                body.append("  " + T.fg(TH.DIM) + T.fit("ETA", 14) + T.RESET +
                            T.fg(TH.TEXT) + st.eta + T.RESET)
            body.append("  " + T.fg(TH.DIM) + T.fit("tempo", 14) + T.RESET +
                        T.fg(TH.TEXT) + f"{int(st.elapsed)}s" + T.RESET)
        done = st and st.done
        keys = ("esc voltar ao scan   q sair" if done else "esc parar crack")
        return self._frame("Crack offline", body, keys)

    def _key_crack(self, k, ch):
        done = self.crack and self.crack.done
        if k == TM.ESCAPE:
            if self.crack_stop:
                self.crack_stop.set()
            self.screen = "scan"
            self._start_scan()
        elif k == "CHAR" and ch == "q":
            self.running = False


# ---------- helpers de modulo ----------
_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _spinner():
    return T.fg(TH.CYAN) + _SPIN[int(time.time() * 10) % len(_SPIN)] + T.RESET


def T_wrap(s, width):
    out, line = [], ""
    for word in s.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = ""
        line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return out
