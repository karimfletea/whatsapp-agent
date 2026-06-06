#!/usr/bin/env bash
# =============================================================================
#  install.sh — Despliega WhatsApp Agent en Ubuntu (como root)
#  Uso: bash install.sh
#  Requiere que /opt/whatsapp-agent/.env ya esté creado antes de correr.
# =============================================================================
set -euo pipefail

APP_DIR="/opt/whatsapp-agent"
SERVICE_NAME="whatsapp-agent"
PY="python3"

# ── Colores ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✔] $*${NC}"; }
warn()  { echo -e "${YELLOW}[!] $*${NC}"; }
error() { echo -e "${RED}[✘] $*${NC}"; exit 1; }

# ── Verificaciones previas ────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Ejecuta como root: sudo bash install.sh"
[[ ! -f "$APP_DIR/.env" ]] && error "Crea $APP_DIR/.env antes de correr este script."

info "Actualizando paquetes del sistema..."
apt-get update -qq

# ── Python ────────────────────────────────────────────────────────────────────
info "Instalando Python 3 y herramientas..."
apt-get install -y -qq python3 python3-venv python3-pip curl gnupg2 lsb-release

# ── PostgreSQL ────────────────────────────────────────────────────────────────
info "Instalando PostgreSQL..."
apt-get install -y -qq postgresql postgresql-contrib

# Leer credenciales de DB desde .env
DB_URL=$(grep -E '^DATABASE_URL=' "$APP_DIR/.env" | cut -d= -f2-)
DB_USER=$(echo "$DB_URL" | sed -E 's|.*://([^:]+):.*|\1|')
DB_PASS=$(echo "$DB_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
DB_NAME=$(echo "$DB_URL" | sed -E 's|.*/([^?]+)|\1|')

info "Creando usuario y base de datos PostgreSQL: $DB_NAME (usuario: $DB_USER)..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

# ── Entorno virtual y dependencias ───────────────────────────────────────────
info "Creando entorno virtual Python..."
cd "$APP_DIR"
$PY -m venv .venv
source .venv/bin/activate

info "Instalando dependencias Python..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── Systemd service ───────────────────────────────────────────────────────────
info "Configurando servicio systemd: $SERVICE_NAME..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=WhatsApp Agent (FastAPI)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
info "Servicio $SERVICE_NAME iniciado."

# ── Caddy (HTTPS automático) ──────────────────────────────────────────────────
if ! command -v caddy &>/dev/null; then
    info "Instalando Caddy..."
    curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] \
https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
fi

# Leer dominio del .env
DOMAIN=$(grep -E '^PUBLIC_BASE_URL=' "$APP_DIR/.env" | sed 's|.*https\?://||;s|/.*||')
[[ -z "$DOMAIN" ]] && DOMAIN="wapli.net"

info "Configurando Caddy para $DOMAIN..."
cat > /etc/caddy/Caddyfile << EOF
${DOMAIN} {
    reverse_proxy 127.0.0.1:8000
    encode gzip
    log {
        output file /var/log/caddy/access.log
    }
}
EOF

mkdir -p /var/log/caddy
systemctl enable caddy
systemctl reload caddy || systemctl restart caddy
info "Caddy configurado para https://${DOMAIN}"

# ── Resultado final ───────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Instalación completada.${NC}"
echo -e "${GREEN}  App:     https://${DOMAIN}${NC}"
echo -e "${GREEN}  Health:  https://${DOMAIN}/health${NC}"
echo -e "${GREEN}  Admin:   https://${DOMAIN}/admin/businesses${NC}"
echo -e "${GREEN}  Logs:    journalctl -u ${SERVICE_NAME} -f${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
