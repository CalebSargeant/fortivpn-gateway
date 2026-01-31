#!/bin/bash

echo "VPN Container Starting..."

# Configuration
VPN_GATEWAY="${VPN_GATEWAY}"
VPN_PORT="${VPN_PORT:-443}"
TRUSTED_CERT="${TRUSTED_CERT}"
COOKIE_FILE="/shared/vpn_cookie.txt"
CONFIG_FILE="/tmp/openfortivpn.conf"

# Reconnection settings
MIN_BACKOFF=30        # Start with 30 seconds
MAX_BACKOFF=900       # Max 15 minutes between retries
BACKOFF_MULTIPLIER=2  # Double the wait time on each failure
MAX_RETRIES=0         # 0 = infinite retries
RETRY_COUNT=0
CURRENT_BACKOFF=$MIN_BACKOFF

# Validate required environment variables
if [ -z "$VPN_GATEWAY" ]; then
    echo "ERROR: VPN_GATEWAY environment variable is required"
    exit 1
fi

echo "VPN Gateway: ${VPN_GATEWAY}:${VPN_PORT}"

# Create openfortivpn configuration file
create_config() {
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
}

# Wait for a fresh cookie file
wait_for_cookie() {
    echo "Waiting for cookie file..."
    while [ ! -f "$COOKIE_FILE" ]; do
        sleep 2
    done
    echo "Cookie file found!"
}

# Connect to VPN
connect_vpn() {
    echo "Starting OpenFortiVPN..."
    cat "$COOKIE_FILE" | openfortivpn --cookie-on-stdin -c "$CONFIG_FILE"
    return $?
}

# Main loop with exponential backoff
create_config

while true; do
    wait_for_cookie

    echo "Attempting VPN connection (attempt $((RETRY_COUNT + 1)))..."
    connect_vpn
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "VPN disconnected cleanly"
        CURRENT_BACKOFF=$MIN_BACKOFF  # Reset backoff on clean disconnect
    else
        echo "VPN connection failed with exit code: $EXIT_CODE"
        RETRY_COUNT=$((RETRY_COUNT + 1))

        if [ $MAX_RETRIES -gt 0 ] && [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
            echo "Max retries ($MAX_RETRIES) reached. Exiting."
            exit 1
        fi
    fi

    echo "Waiting ${CURRENT_BACKOFF} seconds before reconnecting..."
    sleep $CURRENT_BACKOFF

    # Increase backoff for next failure (exponential backoff)
    CURRENT_BACKOFF=$((CURRENT_BACKOFF * BACKOFF_MULTIPLIER))
    if [ $CURRENT_BACKOFF -gt $MAX_BACKOFF ]; then
        CURRENT_BACKOFF=$MAX_BACKOFF
    fi

    # Delete old cookie to trigger refresh from cookie container
    echo "Removing old cookie to request fresh authentication..."
    rm -f "$COOKIE_FILE"
done
