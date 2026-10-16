"""Entry point: python -m airscope  [--demo] [--wordlist PATH]"""
import argparse
import sys

from . import deps
from . import theme as TH
from . import textutil as T


def _c(s, color):
    return T.fg(color) + s + T.RESET


def preflight():
    """Checa plataforma, privilegio e dependencias. Retorna True se pode seguir no modo real."""
    ok = True
    if not deps.is_linux():
        print(_c("airscope precisa de Linux pro modo real (monitor mode).", TH.RED))
        print(_c("No Windows/macOS use --demo pra ver a interface, ou rode o crack offline "
                 "direto no hashcat.", TH.DIM))
        return False
    all_ok, missing, report = deps.check_all()
    print(_c("Dependencias:", TH.CYAN))
    for tool, path, pkg, desc, req in report:
        mark = _c("✔", TH.GREEN) if path else (_c("✗", TH.RED) if req else _c("○", TH.YELLOW))
        tag = "" if req else _c(" (opcional)", TH.DIM)
        line = f"  {mark} {tool:<16}"
        line += _c(path or f"faltando — apt install {pkg}", TH.TEXT if path else TH.DIM)
        print(line + tag)
    print()
    if not all_ok:
        print(_c("Instale o que falta (obrigatorio) e rode de novo:", TH.YELLOW))
        pkgs = sorted({pkg for t, p, pkg, d, r in report if r and not p})
        print(_c(f"  sudo apt install {' '.join(pkgs)}", TH.WHITE))
        ok = False
    if not deps.is_root():
        print(_c("Monitor mode e deauth exigem root. Rode com sudo.", TH.YELLOW))
        ok = False
    if not deps.has_cracker():
        print(_c("Nenhum cracker (aircrack-ng/hashcat) encontrado — captura funciona, "
                 "mas o crack offline nao.", TH.YELLOW))
    return ok


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="airscope",
        description="Orquestrador de auditoria Wi-Fi em TUI (CentralTech). Uso autorizado apenas.")
    p.add_argument("--demo", action="store_true",
                   help="roda com dados simulados, sem hardware nem root (pra testar a UI)")
    p.add_argument("--wordlist", default="/usr/share/wordlists/rockyou.txt",
                   help="dicionario padrao pro crack offline")
    p.add_argument("--no-links", action="store_true", help="desliga os hyperlinks OSC-8 do banner")
    p.add_argument("--version", action="store_true")
    args = p.parse_args(argv)

    if args.version:
        print(f"airscope {TH.VERSION} — CentralTech Solutions")
        return 0

    from .app import App
    if args.demo:
        from .backend.demo import DemoBackend
        backend = DemoBackend()
    else:
        if not preflight():
            print()
            print(_c("Dica: rode `python -m airscope --demo` pra ver a interface sem hardware.", TH.DIM))
            return 1
        from .backend.tools import ToolsBackend
        backend = ToolsBackend()

    app = App(backend, default_wordlist=args.wordlist)
    app.links_on = not args.no_links
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    print(T.BOLD + T.fg(TH.WHITE) + "Central" + T.fg(TH.CYAN) + "Tech" + T.RESET +
          T.fg(TH.DIM) + " · airscope — use com responsabilidade." + T.RESET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
