#!/usr/bin/env bash
# Set up Lab Grader on a fresh Ubuntu 22.04/24.04 server (e.g. Oracle Cloud's free Arm VM).
# Run from the repository folder:
#
#     sudo bash scripts/server_setup.sh [grader.example.org]
#
# Installs Docker, opens ports 80/443, builds and starts the stack, puts HTTPS in front
# (Caddy, certificates from Let's Encrypt) and schedules a nightly database backup.
# Without a domain it uses <your-ip>.sslip.io. Safe to run again.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run with sudo: sudo bash scripts/server_setup.sh [domain]"; exit 1; }
cd "$(dirname "$0")/.."
ROOT=$PWD
OWNER=${SUDO_USER:-root}

echo "== packages and Docker"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git make python3 cron >/dev/null
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker cron
[ "$OWNER" != root ] && usermod -aG docker "$OWNER"

echo "== firewall: allow 80 and 443"
# Oracle's Ubuntu images reject everything but SSH in iptables, on top of the cloud security list
for port in 80 443; do
  iptables -C INPUT -p tcp --dport $port -j ACCEPT 2>/dev/null ||
    iptables -I INPUT -p tcp --dport $port -j ACCEPT
done
command -v netfilter-persistent >/dev/null && netfilter-persistent save >/dev/null 2>&1 || true

mem_mb=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
if [ "$mem_mb" -lt 4000 ] && ! swapon --show | grep -q /swapfile; then
  echo "== ${mem_mb} MB of memory: adding 4 GB of swap"
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q /swapfile /etc/fstab || echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

echo "== .env"
domain=${1:-}
if [ -z "$domain" ]; then
  ip=$(curl -fsS https://api.ipify.org)
  domain="${ip//./-}.sslip.io"
fi
[ -f .env ] || sudo -u "$OWNER" python3 scripts/init_env.py
set_env() {   # set_env KEY VALUE: replace the line, or add it
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
set_env DOMAIN "$domain"
set_env PUBLIC_URL "https://$domain"
set_env COOKIE_SECURE 1
set_env APP_BIND 127.0.0.1
cpus=$(nproc)
set_env GRADING_WORKERS "$cpus"
set_env SANDBOX_MAX_CONCURRENT "$cpus"
chown "$OWNER" .env && chmod 600 .env
mkdir -p secrets backups && chown "$OWNER" secrets backups

echo "== build and start (the first build takes 10 to 20 minutes)"
make up
docker compose --profile https up -d caddy

echo "== nightly backup at 02:30, keeping 14 days"
job="30 2 * * * cd '$ROOT' && make backup >/dev/null 2>&1 && find backups -name '*.sql.gz' -mtime +14 -delete"
( crontab -u "$OWNER" -l 2>/dev/null | grep -v 'make backup' || true; echo "$job" ) | crontab -u "$OWNER" -

pw=$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2-)
echo
echo "Dashboard: https://$domain   login: ta / $pw"
echo "The certificate is issued on the first visit; if it fails, check that ports 80 and 443"
echo "are open in the cloud firewall (Oracle: VCN > Security List > Ingress Rules)."
