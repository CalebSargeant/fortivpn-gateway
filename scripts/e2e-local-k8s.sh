#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-networking}"
APP_LABEL="${APP_LABEL:-app=fortivpn-gateway}"
WAIT_TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-180}"
TAIL_LINES="${TAIL_LINES:-300}"

echo "==> FortiVPN local E2E validation"
echo "Namespace: ${NAMESPACE}"
echo "Label selector: ${APP_LABEL}"
echo "Wait timeout: ${WAIT_TIMEOUT_SECONDS}s"
echo

if ! command -v kubectl >/dev/null 2>&1; then
    echo "ERROR: kubectl is required"
    exit 1
fi

echo "==> Checking deployment exists"
kubectl -n "${NAMESPACE}" get deployment fortivpn-gateway >/dev/null

echo "==> Waiting for pod to be scheduled"
START_TS=$(date +%s)
POD_NAME=""
while true; do
    POD_NAME="$(kubectl -n "${NAMESPACE}" get pods -l "${APP_LABEL}" --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true)"
    if [[ -n "${POD_NAME}" ]]; then
        break
    fi

    NOW_TS=$(date +%s)
    if (( NOW_TS - START_TS > WAIT_TIMEOUT_SECONDS )); then
        echo "ERROR: Timed out waiting for pod matching ${APP_LABEL}"
        exit 1
    fi
    sleep 2
done

echo "Pod: ${POD_NAME}"
echo

echo "==> Pod status"
kubectl -n "${NAMESPACE}" get pod "${POD_NAME}" -o wide
echo

echo "==> Waiting for all containers to become ready (best-effort)"
if ! kubectl -n "${NAMESPACE}" wait --for=condition=Ready "pod/${POD_NAME}" --timeout="${WAIT_TIMEOUT_SECONDS}s" >/dev/null 2>&1; then
    echo "WARNING: Pod did not become fully Ready within timeout; continuing with log-based checks"
fi

echo
echo "==> Collecting recent logs"
COOKIE_LOGS="$(kubectl -n "${NAMESPACE}" logs "pod/${POD_NAME}" -c cookie --tail="${TAIL_LINES}" 2>&1 || true)"
VPN_LOGS="$(kubectl -n "${NAMESPACE}" logs "pod/${POD_NAME}" -c vpn --tail="${TAIL_LINES}" 2>&1 || true)"
BGP_LOGS="$(kubectl -n "${NAMESPACE}" logs "pod/${POD_NAME}" -c bgp --tail="${TAIL_LINES}" 2>&1 || true)"

echo "-- cookie (tail ${TAIL_LINES}) --"
echo "${COOKIE_LOGS}"
echo
echo "-- vpn (tail ${TAIL_LINES}) --"
echo "${VPN_LOGS}"
echo
echo "-- bgp (tail ${TAIL_LINES}) --"
echo "${BGP_LOGS}"
echo

echo "==> Evaluating pass/fail criteria"
COOKIE_OK=false
VPN_OK=false
BGP_OK=false

if grep -Eqi "Cookie extraction completed successfully|Found primary session cookie|Using alternative VPN cookies" <<<"${COOKIE_LOGS}"; then
    COOKIE_OK=true
fi

if grep -Eqi "Tunnel is up and running|Connected to gateway|ppp[0-9]+.*UP|VPN interface .* is up" <<<"${VPN_LOGS}"; then
    VPN_OK=true
fi

if grep -Eqi "Established|BGP session|BIRD.*ready|VPN interface detected" <<<"${BGP_LOGS}"; then
    BGP_OK=true
fi

echo "cookie: ${COOKIE_OK}"
echo "vpn:    ${VPN_OK}"
echo "bgp:    ${BGP_OK}"
echo

if [[ "${COOKIE_OK}" == "true" && "${VPN_OK}" == "true" && "${BGP_OK}" == "true" ]]; then
    echo "PASS: End-to-end flow looks healthy (cookie -> VPN -> BGP)."
    exit 0
fi

echo "FAIL: End-to-end flow is not healthy."
echo "Next checks:"
echo "  - Cookie screenshots in container /tmp/fortivpn_*.png"
echo "  - cookie_auth.py logs for SAML callback/cookie extraction"
echo "  - openfortivpn logs for tunnel establishment"
echo "  - BIRD protocol status via: kubectl -n ${NAMESPACE} exec ${POD_NAME} -c bgp -- birdc show protocols all"
exit 1
