"""Modelo de dados e interface comum dos backends (real e demo)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Interface:
    name: str                 # wlan0
    driver: str = ""
    chipset: str = ""
    monitor: bool = False     # ja esta em monitor mode?
    mon_name: str = ""        # wlan0mon quando em monitor


@dataclass
class Network:
    bssid: str                # AA:BB:CC:DD:EE:FF
    channel: int = 0
    power: int = 0            # dBm (negativo; mais perto de 0 = mais forte)
    enc: str = "WPA2"         # OPN / WEP / WPA / WPA2 / WPA3
    cipher: str = ""
    auth: str = ""
    essid: str = ""
    clients: int = 0
    beacons: int = 0
    wps: bool = False

    @property
    def hidden(self) -> bool:
        return not self.essid or self.essid.startswith("\x00")

    @property
    def crackable(self) -> bool:
        # handshake WPA/WPA2-PSK e o caminho suportado
        return self.enc.startswith("WPA") and self.enc != "WPA3" and "MGT" not in self.auth


@dataclass
class Client:
    mac: str
    bssid: str = ""
    power: int = 0
    packets: int = 0


@dataclass
class CaptureState:
    network: Network
    running: bool = False
    handshake: bool = False
    pmkid: bool = False
    deauths_sent: int = 0
    clients: list = field(default_factory=list)
    started: float = field(default_factory=time.time)
    cap_path: str = ""

    @property
    def elapsed(self) -> float:
        return time.time() - self.started


@dataclass
class CrackState:
    network: Network
    wordlist: str = ""
    running: bool = False
    done: bool = False
    found: bool = False
    password: str = ""
    progress: float = 0.0     # 0..1
    speed: str = ""           # "412.5 kH/s"
    tried: int = 0
    total: int = 0
    eta: str = ""
    started: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started


class Backend:
    """Interface que a UI consome. Implementada por ToolsBackend e DemoBackend."""

    demo = False

    def list_interfaces(self) -> list[Interface]:
        raise NotImplementedError

    def enable_monitor(self, iface: Interface) -> Interface:
        raise NotImplementedError

    def disable_monitor(self, iface: Interface) -> Interface:
        raise NotImplementedError

    # Scan: chama on_update(list[Network]) periodicamente ate stop_event ser setado.
    def scan(self, iface: Interface, on_update: Callable, stop_event) -> None:
        raise NotImplementedError

    # Captura: chama on_update(CaptureState) ate handshake ou stop.
    def capture(self, iface: Interface, net: Network, on_update: Callable, stop_event,
                deauth: bool = True) -> CaptureState:
        raise NotImplementedError

    # Crack: chama on_update(CrackState) ate achar/terminar/stop.
    def crack(self, cap: CaptureState, wordlist: str, on_update: Callable, stop_event) -> CrackState:
        raise NotImplementedError


def power_bars(power: int) -> int:
    """dBm -> 0..4 barrinhas de sinal."""
    if power >= -50:
        return 4
    if power >= -62:
        return 3
    if power >= -74:
        return 2
    if power >= -84:
        return 1
    return 0
