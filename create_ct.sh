#!/usr/bin/env bash
# ============================================================
#  FarmaciReminder — Creazione CT su Proxmox
#  Da eseguire sulla shell di Proxmox (nodo host)
#
#  Uso:
#    bash create_ct.sh
#
#  Cosa fa:
#    1. Scarica il template Debian 12 se non presente
#    2. Crea il CT con le risorse configurate
#    3. Avvia il CT
#    4. Copia il progetto nel CT
#    5. Esegue install.sh nel CT interattivamente
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

header()  { echo -e "\n${CYAN}${BOLD}==> $1${RESET}"; }
success() { echo -e "${GREEN}✔ $1${RESET}"; }
warn()    { echo -e "${YELLOW}⚠ $1${RESET}"; }
error()   { echo -e "${RED}✘ $1${RESET}"; exit 1; }
ask()     { echo -e "${BOLD}$1${RESET}"; }

# ── Controllo che siamo su Proxmox ──────────────────────────
[[ ! -f /etc/pve/storage.cfg ]] && error "Questo script deve essere eseguito su un nodo Proxmox"

clear
echo -e "${CYAN}${BOLD}"
cat << 'EOF'
  ___                          _
 | __|_ _ _ _ _ __  __ _ __(_)
 | _/ _` | '_| '  \/ _` / _| |
 |_|\__,_|_| |_|_|_\__,_\__|_|
  ___              _         _
 | _ \___ _ __ (_)_ _  __| |___ _ _
 |   / -_) '  \| | ' \/ _` / -_) '_|
 |_|_\___|_|_|_|_|_||_\__,_\___|_|

  💊 Creazione CT su Proxmox
EOF
echo -e "${RESET}"

# ── Parametri CT ─────────────────────────────────────────────
header "Configurazione CT"

ask "🔢 ID del CT [es: 200]:"
read -r CT_ID
[[ -z "$CT_ID" ]] && error "ID CT obbligatorio"
pct status "$CT_ID" &>/dev/null && error "CT $CT_ID esiste già"

ask "📛 Hostname [farmaci]:"
read -r CT_HOSTNAME
CT_HOSTNAME="${CT_HOSTNAME:-farmaci}"

ask "🔒 Password root del CT:"
read -rs CT_PASSWORD
echo
[[ -z "$CT_PASSWORD" ]] && error "Password obbligatoria"

ask "💾 Storage Proxmox [local-lvm]:"
read -r CT_STORAGE
CT_STORAGE="${CT_STORAGE:-local-lvm}"

ask "💿 Dimensione disco [4] GB:"
read -r CT_DISK
CT_DISK="${CT_DISK:-4}"

ask "🧠 RAM [512] MB:"
read -r CT_RAM
CT_RAM="${CT_RAM:-512}"

ask "⚙️  CPU cores [1]:"
read -r CT_CORES
CT_CORES="${CT_CORES:-1}"

ask "🌐 Bridge di rete [vmbr0]:"
read -r CT_BRIDGE
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"

ask "📡 IP statico (es: 192.168.1.100/24) oppure 'dhcp':"
read -r CT_IP
CT_IP="${CT_IP:-dhcp}"

if [[ "$CT_IP" != "dhcp" ]]; then
    ask "🚪 Gateway (es: 192.168.1.1):"
    read -r CT_GW
fi

ask "🔌 Porta app [8000]:"
read -r APP_PORT
APP_PORT="${APP_PORT:-8000}"

# ── Riepilogo ────────────────────────────────────────────────
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${RESET}"
echo -e "  CT ID:      ${CYAN}${CT_ID}${RESET}"
echo -e "  Hostname:   ${CYAN}${CT_HOSTNAME}${RESET}"
echo -e "  Storage:    ${CYAN}${CT_STORAGE}${RESET}"
echo -e "  Disco:      ${CYAN}${CT_DISK}GB${RESET}"
echo -e "  RAM:        ${CYAN}${CT_RAM}MB${RESET}"
echo -e "  Cores:      ${CYAN}${CT_CORES}${RESET}"
echo -e "  IP:         ${CYAN}${CT_IP}${RESET}"
echo -e "  Porta app:  ${CYAN}${APP_PORT}${RESET}"
echo -e "${BOLD}──────────────────────────────────────────────${RESET}"
ask "\nCreare il CT? [s/N]:"
read -r CONFIRM
[[ "${CONFIRM,,}" != "s" ]] && { warn "Annullato."; exit 0; }

# ── Scarica template Debian 12 ───────────────────────────────
header "Template Debian 12"
TEMPLATE_STORAGE="local"
TEMPLATE=$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep "debian-12" | tail -1 | awk '{print $1}')

if [[ -z "$TEMPLATE" ]]; then
    warn "Template Debian 12 non trovato, download in corso..."
    pveam update > /dev/null
    TEMPLATE_NAME=$(pveam available --section system | grep "debian-12" | tail -1 | awk '{print $2}')
    [[ -z "$TEMPLATE_NAME" ]] && error "Nessun template Debian 12 disponibile"
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE_NAME"
    TEMPLATE="${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE_NAME}"
fi
success "Template: ${TEMPLATE}"

# ── Crea CT ──────────────────────────────────────────────────
header "Creazione CT ${CT_ID}"

if [[ "$CT_IP" == "dhcp" ]]; then
    NET_CONFIG="name=eth0,bridge=${CT_BRIDGE},ip=dhcp"
else
    NET_CONFIG="name=eth0,bridge=${CT_BRIDGE},ip=${CT_IP}"
    [[ -n "${CT_GW:-}" ]] && NET_CONFIG="${NET_CONFIG},gw=${CT_GW}"
fi

pct create "$CT_ID" "$TEMPLATE" \
    --hostname "$CT_HOSTNAME" \
    --password "$CT_PASSWORD" \
    --storage "$CT_STORAGE" \
    --rootfs "${CT_STORAGE}:${CT_DISK}" \
    --memory "$CT_RAM" \
    --cores "$CT_CORES" \
    --net0 "$NET_CONFIG" \
    --onboot 1 \
    --start 1 \
    --unprivileged 1 \
    --features nesting=1

success "CT ${CT_ID} creato e avviato"

# ── Attendi avvio ────────────────────────────────────────────
header "Attesa avvio CT"
echo -n "  Aspetto che il CT sia pronto"
for i in {1..20}; do
    sleep 2
    echo -n "."
    if pct exec "$CT_ID" -- test -f /etc/debian_version 2>/dev/null; then
        echo ""
        success "CT pronto"
        break
    fi
done

# ── Installa curl e bash nel CT ──────────────────────────────
header "Preparazione CT"
pct exec "$CT_ID" -- bash -c "apt-get update -qq && apt-get install -y --no-install-recommends curl bash > /dev/null 2>&1"
success "Ambiente base installato"

# ── Copia il progetto nel CT ─────────────────────────────────
header "Copia progetto nel CT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Crea un archivio temporaneo escludendo .venv e __pycache__
TMP_ARCHIVE="/tmp/farmaci_reminder_$$.tar.gz"
tar -czf "$TMP_ARCHIVE" \
    --exclude=".venv" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude=".git" \
    --exclude="data/*.db" \
    --exclude="logs/*.log" \
    -C "$(dirname "$SCRIPT_DIR")" \
    "$(basename "$SCRIPT_DIR")"

pct push "$CT_ID" "$TMP_ARCHIVE" /tmp/farmaci_reminder.tar.gz
rm -f "$TMP_ARCHIVE"

pct exec "$CT_ID" -- bash -c "mkdir -p /opt && tar -xzf /tmp/farmaci_reminder.tar.gz -C /opt/ && mv /opt/$(basename "$SCRIPT_DIR") /opt/farmaci_reminder 2>/dev/null || true && rm /tmp/farmaci_reminder.tar.gz"
success "Progetto copiato in /opt/farmaci_reminder"

# ── Esegui install.sh nel CT ─────────────────────────────────
header "Avvio installazione nel CT"
echo ""
warn "Verrai ora connesso al CT per completare l'installazione interattiva."
warn "Segui le istruzioni a schermo."
echo ""
sleep 2

pct exec "$CT_ID" -- bash /opt/farmaci_reminder/install.sh

# ── Recupera IP per riepilogo ────────────────────────────────
CT_REAL_IP=$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}${BOLD}"
echo -e "  ✅ CT ${CT_ID} pronto! — FarmaciReminder 💊"
echo -e "${RESET}"
echo -e "  🌐 Accedi a: ${CYAN}http://${CT_REAL_IP}:${APP_PORT}${RESET}"
echo -e "  🖥️  Shell CT: ${CYAN}pct enter ${CT_ID}${RESET}"
echo -e "  📋 Log app:  ${CYAN}pct exec ${CT_ID} -- journalctl -u farmaci_reminder -f${RESET}"
echo -e "  🔄 Riavvia:  ${CYAN}pct exec ${CT_ID} -- systemctl restart farmaci_reminder${RESET}"
echo ""

