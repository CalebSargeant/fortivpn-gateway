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

echo "Generated BIRD config:"
cat /etc/bird/bird.conf
echo "---"

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "IP forwarding enabled"

# Wait for VPN to be established (wait for ppp0 or similar interface)
echo "Waiting for VPN interface..."
while ! ip link show | grep -q "ppp0\|tun0"; do
    sleep 5
done
echo "VPN interface detected!"

# Show network state for debugging
echo "Network interfaces:"
ip addr show
echo "---"
echo "Routing table:"
ip route show
echo "---"

# Test connectivity to BGP neighbor
echo "Testing connectivity to BGP neighbor ${BGP_NEIGHBOR_IP}..."
if ping -c 3 -W 2 ${BGP_NEIGHBOR_IP} > /dev/null 2>&1; then
    echo "BGP neighbor is reachable via ICMP"
else
    echo "WARNING: BGP neighbor ${BGP_NEIGHBOR_IP} is NOT reachable via ICMP"
    echo "BGP session may fail to establish"
fi

# Start BIRD
echo "Starting BIRD BGP daemon..."
exec /usr/sbin/bird -f -c /etc/bird/bird.conf -d
