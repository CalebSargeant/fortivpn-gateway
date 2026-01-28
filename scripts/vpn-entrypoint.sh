#!/bin/bash
set -e

echo "VPN Container Starting..."

# Configuration
VPN_GATEWAY="${VPN_GATEWAY}"
VPN_PORT="${VPN_PORT:-443}"
TRUSTED_CERT="${TRUSTED_CERT}"
COOKIE_FILE="/shared/vpn_cookie.txt"
CONFIG_FILE="/tmp/openfortivpn.conf"

# Validate required environment variables
if [ -z "$VPN_GATEWAY" ]; then
    echo "ERROR: VPN_GATEWAY environment variable is required"
    exit 1
fi

echo "VPN Gateway: ${VPN_GATEWAY}:${VPN_PORT}"

# Create openfortivpn configuration file
cat > "$CONFIG_FILE" << EOF
host = ${VPN_GATEWAY}
port = ${VPN_PORT}
set-routes = 1
set-dns = 1
pppd-use-peerdns = 1
EOF

# Add trusted cert if provided
if [ -n "$TRUSTED_CERT" ]; then
    echo "trusted-cert = ${TRUSTED_CERT}" >> "$CONFIG_FILE"
fi

# Wait for cookie file to be created
echo "Waiting for cookie file ..."
while [ ! -f "$COOKIE_FILE" ]; do
    sleep 2
done
echo "Cookie file found!"

# Start openfortivpn with cookie
echo "Starting OpenFortiVPN..."
exec cat "$COOKIE_FILE" | openfortivpn --cookie-on-stdin -c "$CONFIG_FILE"
