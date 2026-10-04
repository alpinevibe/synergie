#!/usr/bin/env bash
# ============================================================================
#  Synergie — installation du service et du vhost public.
#
#  Usage :  bash deploy/installer.sh
#
#  - installe le service systemd « synergie » (127.0.0.1:8077) ;
#  - pose le vhost nginx synergie.alpinevibe.fr (proxy inverse, HTTPS) ;
#  - obtient le certificat Let's Encrypt s'il manque ;
#  - teste la configuration nginx AVANT de recharger (aucune coupure).
#  Idempotent : on peut le relancer après chaque mise à jour.
# ============================================================================
set -euo pipefail

racine="$(cd "$(dirname "$0")/.." && pwd)"
app="synergie"
adresse="${app}.alpinevibe.fr"

echo "== 1. Service systemd =="
sudo install -m 644 "$racine/deploy/synergie.service" "/etc/systemd/system/${app}.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${app}.service"
sudo systemctl restart "${app}.service"
sleep 2
systemctl --no-pager --lines=0 status "${app}.service" | head -4

echo "== 2. Vérification locale =="
curl -fsS "http://127.0.0.1:8077/api/sante" || { echo "le service ne répond pas" >&2; exit 1; }
echo

echo "== 3. Vhost nginx (HTTP d'abord, pour le défi Let's Encrypt) =="
# On retire le bloc HTTPS tant que le certificat n'existe pas.
if [ -f "/etc/letsencrypt/live/${adresse}/fullchain.pem" ]; then
  sudo install -m 644 "$racine/deploy/nginx-synergie.conf" "/etc/nginx/sites-available/${app}"
else
  awk '/^server {/{n++} n<2{print}' "$racine/deploy/nginx-synergie.conf" \
    | sudo tee "/etc/nginx/sites-available/${app}" >/dev/null
fi
sudo ln -sf "/etc/nginx/sites-available/${app}" "/etc/nginx/sites-enabled/${app}"
sudo nginx -t
sudo systemctl reload nginx

echo "== 4. Certificat =="
if [ ! -f "/etc/letsencrypt/live/${adresse}/fullchain.pem" ]; then
  sudo certbot --nginx -d "${adresse}" --non-interactive --agree-tos \
       --register-unsafely-without-email --redirect \
    && sudo install -m 644 "$racine/deploy/nginx-synergie.conf" \
         "/etc/nginx/sites-available/${app}" \
    && sudo nginx -t && sudo systemctl reload nginx
else
  echo "   certificat déjà présent"
fi

echo "== 5. Test public =="
curl -fsS "https://${adresse}/api/sante" && echo
echo "Synergie est en ligne : https://${adresse}/"
