"""Checagem de dependencias externas e de privilegio/plataforma."""
import os
import shutil
import sys

# ferramenta -> (pacote sugerido, pra que serve, obrigatoria?)
TOOLS = {
    "iw": ("iw", "listar/gerenciar interfaces wireless", True),
    "airmon-ng": ("aircrack-ng", "ativar monitor mode", True),
    "airodump-ng": ("aircrack-ng", "escanear redes e capturar handshake", True),
    "aireplay-ng": ("aircrack-ng", "deauth pra forcar reconexao (opcional)", False),
    "aircrack-ng": ("aircrack-ng", "crack offline do handshake", False),
    "hashcat": ("hashcat", "crack offline acelerado por GPU (opcional)", False),
    "hcxpcapngtool": ("hcxtools", "converter .cap -> formato 22000 do hashcat (opcional)", False),
}


def which(tool):
    return shutil.which(tool)


def check_all():
    """Retorna (ok, faltando_obrigatorias, relatorio[list[(tool,path,pkg,desc,req)]])."""
    report = []
    missing_required = []
    for tool, (pkg, desc, req) in TOOLS.items():
        path = which(tool)
        report.append((tool, path, pkg, desc, req))
        if req and not path:
            missing_required.append((tool, pkg))
    return (not missing_required), missing_required, report


def is_linux():
    return sys.platform.startswith("linux")


def is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def has_cracker():
    return bool(which("aircrack-ng") or which("hashcat"))
