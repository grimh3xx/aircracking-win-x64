<div align="center">

# aircrackwin-x64

**Orquestrador de auditoria Wi-Fi em TUI** — captura de handshake WPA/WPA2 e crack offline
numa interface de terminal interativa. Python puro, **zero dependências**.

`CentralTech Solutions` · [centraltechpc.com](https://centraltechpc.com) · [github.com/grimh3xx](https://github.com/grimh3xx)

</div>

---

> ⚠️ **Uso autorizado apenas.** Esta ferramenta só deve ser usada em redes que **você possui**
> ou tem **permissão explícita e por escrito** para auditar. Capturar handshake e enviar deauth
> em redes de terceiros sem autorização é crime (Brasil: Lei 12.737/2012; Austrália: Cybercrime
> Act 2001; EUA: CFAA; etc.). Você é o único responsável pelo uso.

O `aircrackwin-x64` **não reimplementa ataque nenhum** — ele orquestra as ferramentas padrão do
`aircrack-ng` e do `hashcat` e mostra tudo numa TUI no estilo do
[usbscope](https://github.com/grimh3xx/usbscope), com a logo da CentralTech em pixel-art. É um
`wifite` com UX caprichada, basicamente.

## Fluxo

```
Interface  →  Scan de redes  →  [autorização]  →  Captura de handshake  →  Crack offline
```

1. **Interface** — escolhe o adaptador wireless; ativa monitor mode (`airmon-ng`).
2. **Scan** — lista as redes ao vivo (`airodump-ng`) com sinal, canal, encriptação e nº de clientes. WPA/WPA2-PSK aparecem em destaque; OPN/WEP/WPA3 em cinza.
3. **Autorização** — confirmação obrigatória de que você tem permissão pra auditar o alvo.
4. **Captura** — captura o handshake (`airodump-ng`), com deauth opcional (`aireplay-ng`) pra forçar a reconexão de um cliente.
5. **Crack** — quebra offline com `hashcat` (`-m 22000`, se o `hcxpcapngtool` estiver presente) ou `aircrack-ng`, com barra de progresso, velocidade e ETA ao vivo.

## Teclas

| Tela | Teclas |
|------|--------|
| **Interfaces** | `↑↓` escolher · `↵` usar (ativa monitor) · `q` sair |
| **Scan** | `↑↓` mover · `↵` capturar · `r` re-scan · `esc` voltar |
| **Captura** | `↵`/`c` partir pro crack (quando pega handshake) · `esc` parar |
| **Wordlist** | digita o caminho · `↵` iniciar · `esc` voltar |
| **Crack** | `esc` voltar ao scan · `q` sair |

## Instalar e rodar

Zero dependências Python — só a stdlib. Precisa de **Python 3.8+** e, pro modo real, das
ferramentas externas abaixo.

```bash
git clone https://github.com/grimh3xx/aircracking-win-x64
cd aircracking-win-x64

# modo demo (qualquer SO, sem hardware nem root) — pra ver a interface:
python3 -m aircrackwin_x64 --demo

# modo real (Linux, root):
sudo python3 -m aircrackwin_x64
sudo python3 -m aircrackwin_x64 --wordlist /usr/share/wordlists/rockyou.txt
```

### Windows (.exe)

Dá pra gerar um executável standalone com PyInstaller (só roda o `--demo`; a auditoria real é Linux):

```powershell
pip install pyinstaller
python -m PyInstaller --onefile --name aircrackwin-x64 aircrackwin_x64_cli.py
.\dist\aircrackwin-x64.exe
```

### Dependências do modo real (Linux)

```bash
sudo apt install aircrack-ng iw          # obrigatórias
sudo apt install hashcat hcxtools        # opcionais (crack acelerado por GPU)
```

O `aircrackwin-x64` checa tudo isso no boot e te diz exatamente o que falta instalar.

## Plataforma

- **Linux** — tudo (monitor mode, scan, captura, crack). É o alvo principal.
- **Windows/macOS** — monitor mode na prática não existe, então só o `--demo` (interface) e,
  se quiser, o crack offline direto no `hashcat` sobre um `.22000` já capturado. A captura em si
  é Linux.

## Estrutura

```
aircrackwin_x64/
  __main__.py        entry point, preflight (root/deps/plataforma), flags
  app.py             TUI: telas, loop interativo, gate de autorização
  banner.py          logo CentralTech em pixel-art (meio-blocos + 24-bit)
  term.py            camada de terminal multiplataforma (POSIX + Windows)
  textutil.py        cor ANSI, largura de UTF-8, barra de progresso, degradê
  theme.py           cores da identidade CentralTech
  deps.py            checagem de ferramentas externas e privilégio
  logo_data.py       dados da logo (gerado de tools/logo_grid.png)
  backend/
    base.py          modelo: Interface, Network, CaptureState, CrackState
    tools.py         backend real — wrappers airmon/airodump/aireplay/aircrack/hashcat
    demo.py          backend sintético (--demo), sem hardware
aircrackwin_x64_cli.py  entry point pro PyInstaller (--onefile)
tools/
  gen_logo_py.py     regera logo_data.py a partir da logo
```

## Como funciona por dentro

- **Scan**: roda `airodump-ng --output-format csv` e faz o parsing do CSV (duas seções: APs e stations) a cada segundo.
- **Captura**: `airodump-ng --bssid X -c canal` grava o `.cap`; em paralelo, `aireplay-ng --deauth` força reconexão. O handshake é detectado rodando `aircrack-ng` no `.cap` periodicamente.
- **Crack**: se tiver `hashcat` + `hcxpcapngtool`, converte o `.cap` pro formato `22000` e roda o hashcat com `--status-json` (progresso ao vivo). Senão, cai pro `aircrack-ng` e faz o parsing da saída.

A UI redesenha num loop com timeout, enquanto threads de fundo alimentam o estado — por isso o scan, a captura e o crack atualizam em tempo real sem travar a interface.

---

<div align="center">
<sub>© CentralTech Solutions — <a href="https://centraltechpc.com">centraltechpc.com</a> · ferramenta de auditoria para uso autorizado</sub>
</div>
