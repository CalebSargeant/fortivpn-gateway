#!/bin/bash
set -e

echo "Cookie Starting..."
echo "Running continuous cookie refresh"

# Run cookie extraction in continuous mode
exec python3 /usr/local/bin/cookie_auth.py
