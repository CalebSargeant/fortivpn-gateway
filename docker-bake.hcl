# docker-bake.hcl
# Docker Bake configuration for fortivpn-gateway

# Variables from environment
variable "VERSION" {
  default = "latest"
}

variable "REGISTRY" {
  default = "ghcr.io"
}

variable "IMAGE_NAME" {
  default = "calebsargeant/fortivpn-gateway"
}

variable "PLATFORMS" {
  default = "linux/amd64,linux/arm64"
}

# Default target group - build all images
group "default" {
  targets = ["cookie", "vpn", "bgp"]
}

# Cookie image
target "cookie" {
  context    = "."
  dockerfile = "Dockerfile.cookie"
  
  platforms = split(",", PLATFORMS)
  
  tags = [
    "${REGISTRY}/${IMAGE_NAME}-cookie:${VERSION}",
    "${REGISTRY}/${IMAGE_NAME}-cookie:latest",
  ]
  
  labels = {
    "org.opencontainers.image.source"      = "https://github.com/CalebSargeant/fortivpn-gateway"
    "org.opencontainers.image.version"     = "${VERSION}"
    "org.opencontainers.image.created"     = timestamp()
    "org.opencontainers.image.description" = "FortiVPN Gateway - Cookie Authentication"
  }
  
  cache-to   = ["type=inline"]
  output     = ["type=image,push=true"]
}

# VPN client image
target "vpn" {
  context    = "."
  dockerfile = "Dockerfile.vpn"
  
  platforms = split(",", PLATFORMS)
  
  tags = [
    "${REGISTRY}/${IMAGE_NAME}-vpn:${VERSION}",
    "${REGISTRY}/${IMAGE_NAME}-vpn:latest",
  ]
  
  labels = {
    "org.opencontainers.image.source"      = "https://github.com/CalebSargeant/fortivpn-gateway"
    "org.opencontainers.image.version"     = "${VERSION}"
    "org.opencontainers.image.created"     = timestamp()
    "org.opencontainers.image.description" = "FortiVPN Gateway - OpenFortiVPN Client"
  }
  
  cache-to   = ["type=inline"]
  output     = ["type=image,push=true"]
}

# BGP daemon image
target "bgp" {
  context    = "."
  dockerfile = "Dockerfile.bgp"
  
  platforms = split(",", PLATFORMS)
  
  tags = [
    "${REGISTRY}/${IMAGE_NAME}-bgp:${VERSION}",
    "${REGISTRY}/${IMAGE_NAME}-bgp:latest",
  ]
  
  labels = {
    "org.opencontainers.image.source"      = "https://github.com/CalebSargeant/fortivpn-gateway"
    "org.opencontainers.image.version"     = "${VERSION}"
    "org.opencontainers.image.created"     = timestamp()
    "org.opencontainers.image.description" = "FortiVPN Gateway - BIRD BGP Daemon"
  }
  
  cache-to   = ["type=inline"]
  output     = ["type=image,push=true"]
}

# Group for building all services
group "all" {
  targets = ["cookie", "vpn", "bgp"]
}
