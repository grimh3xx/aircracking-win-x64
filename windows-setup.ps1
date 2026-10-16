<#
    windows-setup.ps1 — prepara o caminho WSL2 + usbipd pra rodar o aircrackwin-x64
    (captura real de Wi-Fi) a partir do Windows, passando um adaptador USB pro Linux.

    IMPORTANTE — leia antes:
    - O Windows NAO captura Wi-Fi em monitor mode. Este script NAO faz o Windows capturar.
      Ele instala a plumbing pra rodar o LINUX por baixo (WSL2) e passar o teu adaptador
      USB pra la com o usbipd.
    - O passo que pode falhar e o monitor mode dentro do WSL2: o kernel padrao do WSL
      geralmente NAO tem o driver do adaptador nem o mac80211. Se nao aparecer uma
      interface wlan la dentro, voce precisa de um kernel WSL compilado com suporte
      wireless — ou use uma VM Kali (rota mais garantida, veja o README).
    - Precisa de um adaptador USB que suporte monitor mode (ex.: Alfa AWUS036NHA/ACH,
      chipset RTL8812AU). O Wi-Fi interno do notebook nao serve.

    Uso (PowerShell como ADMINISTRADOR):
        Set-ExecutionPolicy -Scope Process Bypass -Force
        .\windows-setup.ps1
#>

$ErrorActionPreference = "Stop"

function Info($m)  { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "[!] $m" -ForegroundColor Yellow }
function Step($m)  { Write-Host "`n=== $m ===" -ForegroundColor White }

# precisa de admin
$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
          ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Warn "Rode este script num PowerShell como Administrador."
    exit 1
}

Step "1/5  WSL2"
if (-not (Get-Command wsl -ErrorAction SilentlyContinue)) {
    Info "Instalando o WSL2 (pode pedir reiniciar; depois rode o script de novo)…"
    wsl --install
    Warn "Se pediu reiniciar: reinicie, abra o Ubuntu pra criar o usuario, e rode este script outra vez."
    exit 0
} else {
    wsl --set-default-version 2 | Out-Null
    Ok "WSL disponivel."
}

Step "2/5  usbipd-win (passar USB pro WSL)"
if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    Info "Instalando usbipd-win via winget…"
    winget install --exact --id dorssel.usbipd-win --accept-source-agreements --accept-package-agreements
    Warn "Feche e reabra o PowerShell (admin) pra o comando 'usbipd' entrar no PATH, e rode o script de novo."
    exit 0
} else {
    Ok "usbipd instalado."
}

Step "3/5  aircrack-ng + aircrackwin-x64 dentro do WSL"
Info "Instalando ferramentas no WSL (sudo pode pedir senha)…"
wsl -e bash -lc "sudo apt-get update -y && sudo apt-get install -y aircrack-ng iw hashcat hcxtools python3"
# copia o projeto pro home do WSL se estivermos na pasta do projeto
if (Test-Path ".\aircrackwin_x64\__main__.py") {
    $winPath = (Get-Location).Path
    $wslPath = "/mnt/" + ($winPath.Substring(0,1).ToLower()) + ($winPath.Substring(2) -replace '\\','/')
    wsl -e bash -lc "cp -r '$wslPath' ~/aircrackwin-x64 2>/dev/null; echo 'projeto copiado pra ~/aircrackwin-x64'"
}
Ok "Ferramentas instaladas no WSL."

Step "4/5  Anexar o adaptador USB ao WSL"
Info "Adaptadores USB vistos pelo Windows:"
usbipd list
Write-Host ""
$busid = Read-Host "Digite o BUSID do teu adaptador Wi-Fi (ex.: 2-4), ou Enter pra pular"
if ($busid) {
    try {
        usbipd bind --busid $busid
        usbipd attach --wsl --busid $busid
        Ok "Adaptador $busid anexado ao WSL."
        Warn "Pra reanexar depois de desplugar/reiniciar: usbipd attach --wsl --busid $busid"
    } catch {
        Warn "Falhou ao anexar. Confira o BUSID e se o adaptador esta plugado."
    }
}

Step "5/5  Verificar"
Info "Checando se o adaptador aparece como interface wireless no WSL…"
wsl -e bash -lc "iw dev 2>/dev/null | grep -A2 Interface || echo 'NENHUMA interface wireless no WSL (kernel sem driver — veja o README, rota VM Kali)'"

Write-Host ""
Ok "Setup concluido."
Write-Host @"

Proximos passos (dentro do WSL):
    cd ~/aircrackwin-x64
    sudo python3 -m aircrackwin_x64

Se o passo 5 disse 'NENHUMA interface wireless', o kernel do WSL nao tem o driver
do teu adaptador. Ai a rota confiavel e uma VM Kali com passthrough USB (README).

Uso autorizado apenas: so teste redes que voce possui ou tem permissao por escrito.
"@ -ForegroundColor Gray
