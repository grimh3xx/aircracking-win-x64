"""Backend sintetico: roda sem hardware (--demo). Usado tambem pra screenshots/testes."""
from __future__ import annotations

import random
import time

from .base import Backend, CaptureState, Client, CrackState, Interface, Network


_ESSIDS = [
    ("NET_VIVO-2G4A", "WPA2", 6, -42, 3, True),
    ("CLARO_5G_Casa", "WPA2", 36, -58, 1, False),
    ("TP-Link_4F2C", "WPA2", 11, -67, 0, True),
    ("iPhone de Daniel", "WPA3", 1, -71, 1, False),
    ("CENTRALTECH-LAB", "WPA2", 9, -39, 2, False),
    ("", "WPA2", 3, -80, 0, False),          # oculta
    ("NET_2G_Vizinho", "WPA2", 6, -83, 0, False),
    ("Starlink", "WPA2", 149, -74, 4, False),
    ("HP-Print-5A", "OPN", 1, -77, 0, False),
    ("GVT-OLD", "WEP", 4, -86, 0, False),
]


class DemoBackend(Backend):
    demo = True

    def list_interfaces(self):
        return [
            Interface("wlan0", driver="iwlwifi", chipset="Intel AX210"),
            Interface("wlan1", driver="rt2800usb", chipset="Ralink RT5370 (USB)"),
        ]

    def enable_monitor(self, iface):
        time.sleep(0.4)
        iface.monitor = True
        iface.mon_name = iface.name + "mon"
        return iface

    def disable_monitor(self, iface):
        iface.monitor = False
        iface.mon_name = ""
        return iface

    def scan(self, iface, on_update, stop_event):
        found = []
        order = list(range(len(_ESSIDS)))
        random.shuffle(order)
        i = 0
        while not stop_event.is_set():
            if i < len(order):
                essid, enc, ch, pwr, clients, wps = _ESSIDS[order[i]]
                mac = ":".join(f"{random.randint(0,255):02X}" for _ in range(6))
                found.append(Network(
                    bssid=mac, channel=ch, power=pwr, enc=enc,
                    cipher="CCMP" if enc.startswith("WPA") else ("WEP" if enc == "WEP" else ""),
                    auth="PSK" if enc.startswith("WPA") else "",
                    essid=essid, clients=clients, beacons=random.randint(5, 40), wps=wps))
                i += 1
            # jitter no sinal/beacons dos ja achados
            for n in found:
                n.power = max(-92, min(-30, n.power + random.randint(-2, 2)))
                n.beacons += random.randint(0, 6)
            on_update(list(found))
            stop_event.wait(0.6)

    def capture(self, iface, net, on_update, stop_event, deauth=True):
        st = CaptureState(network=net, running=True,
                          cap_path=f"/tmp/aircrackwin-x64/{net.essid or net.bssid}.cap")
        st.clients = [Client(":".join(f"{random.randint(0,255):02X}" for _ in range(6)),
                             bssid=net.bssid, power=net.power + random.randint(-5, 5),
                             packets=random.randint(10, 200)) for _ in range(max(1, net.clients))]
        # handshake chega em alguns segundos (mais rapido com deauth)
        target = random.uniform(3.0, 6.0) / (1.6 if deauth else 1.0)
        while not stop_event.is_set():
            if deauth and random.random() < 0.5:
                st.deauths_sent += random.randint(1, 5)
            if st.elapsed >= target and not st.handshake:
                st.handshake = True
                st.running = False
                on_update(st)
                return st
            on_update(st)
            stop_event.wait(0.4)
        st.running = False
        return st

    def crack(self, cap, wordlist, on_update, stop_event):
        st = CrackState(network=cap.network, wordlist=wordlist, running=True,
                        total=14344391, speed="0 H/s")  # ~ tamanho da rockyou
        # senha "achada" em ~65% das vezes, numa fracao aleatoria da lista
        will_find = random.random() < 0.65
        hit = random.uniform(0.15, 0.9) if will_find else 1.1
        rate = random.uniform(250_000, 900_000)  # H/s simulado
        while not stop_event.is_set():
            dt = 0.3
            st.tried = min(st.total, st.tried + int(rate * dt))
            st.progress = st.tried / st.total
            st.speed = f"{rate/1000:.1f} kH/s"
            remain = (st.total - st.tried) / rate
            st.eta = f"{int(remain//60)}m{int(remain%60):02d}s"
            if st.progress >= hit:
                st.found = True
                st.done = True
                st.running = False
                st.password = random.choice(
                    ["familia2019", "SenhaForte!23", "vivo12345", "centraltech", "97531086"])
                st.progress = hit
                on_update(st)
                return st
            if st.progress >= 1.0:
                st.done = True
                st.running = False
                on_update(st)
                return st
            on_update(st)
            stop_event.wait(dt)
        st.running = False
        return st
