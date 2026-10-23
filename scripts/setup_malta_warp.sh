#!/usr/bin/env bash
set -euo pipefail

# Only the Malta archive fetch uses this local proxy. Other sources and the
# classifier keep the runner's normal network route.
if [[ "${MALTA_WARP_TERMS_APPROVED:-}" != "true" ]]; then
  echo '::error::Cloudflare WARP terms have not been approved for automated runners.'
  exit 1
fi

. /etc/os-release
test -n "${VERSION_CODENAME:-}"
echo 'Configuring the Cloudflare package repository.'
curl -fsSL --max-time 20 https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --dearmor --yes --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ ${VERSION_CODENAME} main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list >/dev/null
echo 'Installing the Cloudflare WARP client.'
timeout 60s sudo apt-get update -qq
timeout 90s sudo apt-get install -y -qq cloudflare-warp

echo 'Registering and connecting the WARP proxy.'
timeout 20s sudo warp-cli --accept-tos registration new
timeout 20s sudo warp-cli --accept-tos mode proxy
timeout 20s sudo warp-cli --accept-tos proxy port 40000
timeout 20s sudo warp-cli --accept-tos connect

connected=false
for attempt in {1..15}; do
  if timeout 5s warp-cli --accept-tos status | grep -q 'Status update: Connected'; then
    connected=true
    break
  fi
  sleep 2
done
if [[ "$connected" != true ]]; then
  timeout 5s warp-cli --accept-tos status || true
  echo '::error::Cloudflare WARP did not connect.'
  exit 1
fi

proxy='socks5h://127.0.0.1:40000'
curl -fsS --max-time 10 --proxy "$proxy" https://www.cloudflare.com/cdn-cgi/trace | grep -qx 'warp=on'
curl -fsS --compressed --max-time 10 --proxy "$proxy" \
  -H 'Accept: application/json;odata=nometadata' \
  'https://www.gov.mt/en/Government/DOI/Press%20Releases/_api/web/lists/getbytitle(%27Pages%27)/items?%24top=1' \
  | python3 -c 'import json,sys; assert isinstance(json.load(sys.stdin)["value"],list)'

echo "MALTA_WARP_PROXY=$proxy" >> "$GITHUB_ENV"
echo 'Malta archive is reachable through the verified WARP proxy.'
