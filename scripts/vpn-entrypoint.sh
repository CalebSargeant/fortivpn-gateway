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

# VPN interface wait timeout (in seconds)
VPN_INTERFACE_WAIT_TIMEOUT=30

# NAT setup tracking flag
NAT_CONFIGURED=false

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

# Detect active VPN interface
get_active_vpn_interface() {
    # Check for any ppp interface that is UP (ppp0, ppp1, ppp2, etc.)
    # Use 'ip link show up' to list only UP interfaces, then filter for ppp
    # Example matching line: "3: ppp1: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP>"
    local ppp_interface=$(ip link show up | awk '/^[0-9]+: ppp[0-9]+:/ {match($2, /ppp[0-9]+/, arr); print arr[0]; exit}')
    if [ -n "$ppp_interface" ]; then
        echo "$ppp_interface"
        return 0
    fi
    
    # Fallback to tun0 if no ppp interface found
    if ip link show tun0 2>/dev/null | grep -q "UP"; then
        echo "tun0"
        return 0
    fi
    return 1
}

# Setup NAT/masquerading for VPN traffic
setup_nat() {
    # Check if NAT has already been configured
    if [ "$NAT_CONFIGURED" = true ]; then
        echo "NAT already configured, skipping setup"
        return 0
    fi
    
    echo "Setting up NAT/masquerading for VPN traffic..."
    
    # Wait for VPN interface to be up
    local count=0
    local vpn_interface=""
    
    while [ $count -lt $VPN_INTERFACE_WAIT_TIMEOUT ]; do
        vpn_interface=$(get_active_vpn_interface)
        if [ $? -eq 0 ]; then
            echo "VPN interface $vpn_interface is up"
            break
        fi
        sleep 1
        count=$((count + 1))
    done
    
    if [ -z "$vpn_interface" ]; then
        echo "ERROR: VPN interface did not come up within ${VPN_INTERFACE_WAIT_TIMEOUT} seconds"
        return 1
    fi
    
    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    echo "IP forwarding enabled"
    
    # Check if masquerading rule already exists for this interface
    if iptables -t nat -C POSTROUTING -o "$vpn_interface" -j MASQUERADE 2>/dev/null; then
        echo "Masquerading rule for $vpn_interface already exists"
    else
        # Add masquerading rule for the active VPN interface
        # This allows return traffic to work properly
        iptables -t nat -A POSTROUTING -o "$vpn_interface" -j MASQUERADE
        echo "Added masquerading rule for $vpn_interface"
    fi
    
    # Mark NAT as configured
    NAT_CONFIGURED=true
    
    # Show current NAT rules (suppress warning about legacy tables)
    echo "Current NAT rules:"
    iptables -t nat -L POSTROUTING -n -v 2>/dev/null
}

# Connect to VPN
connect_vpn() {
    echo "Starting OpenFortiVPN..."
    
    # Setup NAT in background to run once VPN is established
    setup_nat &
    
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
