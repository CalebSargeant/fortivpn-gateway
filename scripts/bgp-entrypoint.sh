#!/bin/bash
set -e

echo "BGP Container Starting..."

# Required environment variables
: ${BGP_ROUTER_ID:?"BGP_ROUTER_ID is required"}
: ${BGP_LOCAL_AS:?"BGP_LOCAL_AS is required"}
: ${BGP_NEIGHBOR_IP:?"BGP_NEIGHBOR_IP is required"}
: ${BGP_NEIGHBOR_AS:?"BGP_NEIGHBOR_AS is required"}

echo "BGP Configuration:"
echo "  Router ID: ${BGP_ROUTER_ID}"
echo "  Local AS: ${BGP_LOCAL_AS}"
echo "  Neighbor: ${BGP_NEIGHBOR_IP} (AS ${BGP_NEIGHBOR_AS})"

# Generate BIRD config from template
sed -e "s/BGP_ROUTER_ID/${BGP_ROUTER_ID}/g" \
    -e "s/BGP_LOCAL_AS/${BGP_LOCAL_AS}/g" \
    -e "s/BGP_NEIGHBOR_IP/${BGP_NEIGHBOR_IP}/g" \
    -e "s/BGP_NEIGHBOR_AS/${BGP_NEIGHBOR_AS}/g" \
    /etc/bird/bird.conf.template > /etc/bird/bird.conf

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "IP forwarding enabled"

# Wait for VPN to be established (wait for ppp0 or similar interface)
echo "Waiting for VPN interface..."
while ! ip link show | grep -q "ppp0\|tun0"; do
    sleep 5
done
echo "VPN interface detected!"

# Start BIRD
echo "Starting BIRD BGP daemon..."
exec /usr/sbin/bird -f -c /etc/bird/bird.conf -d
