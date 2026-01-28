# FortiVPN Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Kubernetes-based FortiVPN gateway with automatic Microsoft SAML authentication and BGP routing to MikroTik. This project creates a VPN gateway pod that establishes a client-to-site VPN connection and advertises routes via BGP.

## Architecture

This solution uses a multi-container pod architecture with three specialized containers:

```
┌─────────────────────────────────────────────────────────────┐
│ FortiVPN Gateway Pod (hostNetwork: true)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────┐  │
│  │ Cookie           │  │ VPN Container    │  │ BGP       │  │
│  ├──────────────────┤  ├──────────────────┤  ├───────────┤  │
│  │ • Selenium       │  │ • OpenFortiVPN   │  │ • BIRD    │  │
│  │ • 1Password CLI  │  │ • PPP daemon     │  │ • Routing │  │
│  │ • Chrome         │  │ • Cookie auth    │  │ • Peering │  │
│  └────────┬─────────┘  └────────┬─────────┘  └─────┬─────┘  │
│           │                     │                   │       │
│           └─────────┬───────────┘                   │       │
│                     │ /shared volume                │       │
│                     │ (cookie exchange)             │       │
│                     │                               │       │
│                     └───────────────────────────────┘       │
│                         ppp0/tun0 interface                 │
└─────────────────────────────────────────────────────────────┘
                             │
                             │ BGP Peering
                             ▼
                       ┌─────────┐
                       │  Router │
                       └─────────┘
```

### Container Responsibilities

1. **Cookie**
   - Automates Microsoft SAML authentication via Selenium
   - Fetches credentials from 1Password CLI
   - Handles OTP/2FA automatically
   - Continuously refreshes session cookies
   - Shares cookies via `/shared` volume

2. **VPN Container**
   - Runs OpenFortiVPN client
   - Consumes cookies
   - Establishes PPP tunnel
   - Manages VPN routing

3. **BGP Container**
   - Runs BIRD BGP daemon
   - Peers with router
   - Advertises VPN routes
   - Enables network-wide VPN access

## Features

- 🔐 **Automated Authentication**: Microsoft SSO with 1Password CLI integration
- 🔄 **Continuous Operation**: Automatic cookie refresh keeps VPN alive
- 🌐 **BGP Integration**: Routes advertised to your network via MikroTik
- 🏗️ **Microservices**: Clean separation of concerns with pattern
- 🐳 **Cloud Native**: Full Kubernetes deployment with Kustomize
- 🔒 **SOPS Encrypted Secrets**: Production secrets encrypted with age

## Prerequisites

- Kubernetes cluster (tested with k3s)
- Router with BGP support
- FortiVPN gateway with SAML authentication enabled
- 1Password service account
- Microsoft account with VPN access

## Quick Start

### 1. Configure Secrets

```bash
cd k8s/overlays/prod
cp ../../../secret.yaml.example secret.yaml

# Edit with your values:
# - OP_SERVICE_ACCOUNT_TOKEN: 1Password service account token
# - VPN_GATEWAY: Your FortiVPN gateway address
# - BGP_*: Your BGP configuration for MikroTik peering

# Encrypt with SOPS
sops -e secret.yaml > secret.enc.yaml
rm secret.yaml
```

### 2. Deploy to Kubernetes

```bash
kubectl apply -k k8s/overlays/prod
```

### 3. Verify Deployment

```bash
# Check pod status
kubectl get pods -n networking

# Check logs from each container
kubectl logs -n networking fortivpn-gateway-xxx -c cookie
kubectl logs -n networking fortivpn-gateway-xxx -c vpn
kubectl logs -n networking fortivpn-gateway-xxx -c bgp

# Verify BGP peering
kubectl exec -n networking fortivpn-gateway-xxx -c bgp -- birdc show protocols
```

## Configuration

### Environment Variables

#### Cookie
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OP_SERVICE_ACCOUNT_TOKEN` | Yes | - | 1Password service account token |
| `OP_ITEM_NAME` | No | `Microsoft` | 1Password item name |
| `OP_VAULT` | No | `Private` | 1Password vault name |
| `VPN_GATEWAY` | Yes | - | FortiVPN gateway hostname |
| `VPN_PORT` | No | `443` | FortiVPN gateway port |
| `REFRESH_INTERVAL` | No | `3600` | Cookie refresh interval (seconds) |
| `AUTH_TIMEOUT` | No | `60` | Authentication timeout (seconds) |

#### VPN Container
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VPN_GATEWAY` | Yes | - | FortiVPN gateway hostname |
| `VPN_PORT` | No | `443` | FortiVPN gateway port |
| `TRUSTED_CERT` | No | - | Gateway certificate digest for validation (e.g., `pin-sha256:base64digest`) |

#### BGP Container
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BGP_ROUTER_ID` | Yes | - | BGP router ID (typically pod IP) |
| `BGP_LOCAL_AS` | Yes | - | Local AS number (e.g., 65001) |
| `BGP_NEIGHBOR_IP` | Yes | - | MikroTik router IP |
| `BGP_NEIGHBOR_AS` | Yes | - | MikroTik AS number (e.g., 65000) |

## Building Images

### Build all images

```bash
docker buildx bake -f docker-bake.hcl --push
```

### Build specific image

```bash
docker buildx bake -f docker-bake.hcl cookie --push
docker buildx bake -f docker-bake.hcl vpn --push
docker buildx bake -f docker-bake.hcl bgp --push
```

### Build with version tag

```bash
VERSION=v1.0.0 docker buildx bake -f docker-bake.hcl --push
```

## MikroTik BGP Configuration

Configure your MikroTik router to peer with the gateway pod:

```routeros
# Create BGP instance
/routing bgp instance
add name=default as=65000 router-id=192.168.1.1

# Add BGP peer (use pod's hostNetwork IP)
/routing bgp peer
add name=fortivpn-gateway remote-address=192.168.1.100 remote-as=65001 ttl=default

# Configure BGP network
/routing bgp network
add network=0.0.0.0/0  # Or specific networks
```

## Troubleshooting

### Cookie Authentication Fails
- Check 1Password service account has access to credentials
- Verify Microsoft account credentials and OTP configuration
- Check cookie logs: `kubectl logs -n networking <pod> -c cookie`
- Debug screenshots saved to `/tmp/fortivpn_*.png` in container

### VPN Connection Issues
- Ensure pod has privileged access and NET_ADMIN capability
- Check `/dev/ppp` exists in container
- Verify cookie file exists in `/shared` volume
- Check vpn container logs: `kubectl logs -n networking <pod> -c vpn`

### Gateway Certificate Validation Failed
If you see an error like:
```
ERROR: Gateway certificate validation failed, and the certificate digest is not in the local whitelist.
ERROR:     trusted-cert = <certificate-digest>
```

1. Copy the certificate digest from the error message
2. Add it to your secret configuration:
```yaml
TRUSTED_CERT: "pin-sha256:your-certificate-digest-here"
```
3. Update the secret: `kubectl apply -k k8s/overlays/prod`
4. Restart the pod to apply changes

### BGP Not Peering
- Verify MikroTik BGP configuration matches pod settings
- Check pod is using hostNetwork and has correct IP
- Ensure BGP port (179) is accessible
- Check bgp container logs: `kubectl logs -n networking <pod> -c bgp`
- Verify with: `kubectl exec -n networking <pod> -c bgp -- birdc show protocols all`

### VPN Routes Not Propagating
- Check BIRD is learning routes from kernel: `birdc show route protocol kernel`
- Verify BGP export policy in `bird.conf.template`
- Check MikroTik is receiving routes: `/routing bgp advertisements print`

## Security Considerations

- Pod runs with `hostNetwork: true` and `privileged: true`
- Requires NET_ADMIN and NET_RAW capabilities
- Store secrets encrypted with SOPS
- 1Password service account should have minimal permissions
- Consider network policies to restrict pod access

## Development

### Project Structure

```
.
├── cookie_auth.py                    # Cookie extraction script
├── scripts/
│   ├── cookie-entrypoint.sh # Cookie entrypoint
│   ├── vpn-entrypoint.sh            # VPN container entrypoint
│   ├── bgp-entrypoint.sh            # BGP container entrypoint
│   └── bird.conf.template           # BIRD config template
├── Dockerfile.cookie                # Cookie image
├── Dockerfile.vpn                   # VPN client image
├── Dockerfile.bgp                   # BGP daemon image
├── docker-bake.hcl                  # Multi-image build config
├── k8s/
│   ├── base/
│   │   ├── deployment.yaml          # Multi-container deployment
│   │   └── kustomization.yaml
│   └── overlays/
│       └── prod/
│           ├── kustomization.yaml
│           └── secret.enc.yaml      # SOPS encrypted secrets
└── secret.yaml.example              # Secret template
```

## License

MIT License - see [LICENSE](LICENSE) file for details

## Related Projects

- [openfortivpn](https://github.com/adrienverge/openfortivpn) - FortiVPN client

## Contributing

Pull requests welcome! Please ensure:
- Docker images build successfully
- K8s manifests are valid
- Documentation is updated
