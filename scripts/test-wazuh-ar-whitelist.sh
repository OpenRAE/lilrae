#!/usr/bin/env bash
# End-to-end validation of the kali-IP whitelist carve-out (issue #249,
# ADR-021). Drives the wrapper directly on an agent — no Wazuh manager
# rule wiring needed for the in-band proof; the agent-side wrapper is
# the only enforcement point.
#
# This script is the manual-runnable counterpart to
# tests/test_wazuh_active_response.py::TestWazuhActiveResponseWrapper.
# The pytest covers wrapper unit behavior; this script demonstrates the
# end-to-end "AR fires → wrapper consults whitelist → kali traffic
# preserved" story for blue-side debugging when wiring AR rules.
#
# Procedure:
#   1. Sanity check: lab is up; the wrapper exists on aptl-webapp.
#   2. Send a synthetic Wazuh AR `add` command with srcip=kali — assert
#      the wrapper exits 0 and writes a SKIPPED line to active-
#      responses.log. This is the carve-out engaging.
#   3. Send a synthetic Wazuh AR `add` command with srcip=an-arbitrary-
#      attacker — assert the wrapper FORWARDS to the upstream firewall-
#      drop (we mock the upstream with /bin/false so the test doesn't
#      actually mutate iptables; the non-zero exit confirms forward).
#   4. Send a synthetic Wazuh AR `delete` command with srcip=kali —
#      assert the wrapper still forwards (cleanup must always run).
#
# Idempotent — the wrapper appends a line per invocation, and each step
# judges only the lines appended after it started, so lines left by an
# earlier run (or an earlier step) cannot satisfy a check.
#
# Exit 0 = pass; non-zero = fail.

set -euo pipefail

TARGET="${TARGET:-aptl-webapp}"
WRAPPER="${WRAPPER:-/var/ossec/active-response/bin/aptl-firewall-drop}"
WHITELIST="${WHITELIST:-/var/ossec/etc/lists/active-response-whitelist}"
LOG="${LOG:-/var/ossec/logs/active-responses.log}"
KALI_IP="${KALI_IP:-172.20.4.30}"
ATTACKER_IP="${ATTACKER_IP:-10.99.99.99}"

log()  { echo "[test-wazuh-ar-whitelist] $*"; }
fail() { log "FAIL: $*"; exit 1; }
pass() { log "PASS: $*"; }

# --- preflight --------------------------------------------------------------
if ! docker ps --format '{{.Names}}' | grep -q "^${TARGET}$"; then
    fail "${TARGET} not running. Run: lilrae lab start"
fi
if ! docker exec "${TARGET}" test -x "${WRAPPER}"; then
    fail "${WRAPPER} missing/not-executable inside ${TARGET}. Image rebuild needed?"
fi
if ! docker exec "${TARGET}" test -f "${WHITELIST}"; then
    fail "${WHITELIST} missing inside ${TARGET}. Image rebuild needed?"
fi
log "preflight ok: ${TARGET} has wrapper + whitelist"

# Number of lines in ${LOG} on ${TARGET} (0 when it does not exist yet).
# Record it before a step, then judge the step with log_has_new_line.
log_line_count() {
    local count
    count=$(docker exec "${TARGET}" grep -c '' "${LOG}" 2>/dev/null) || true
    echo "${count:-0}"
}

# log_has_new_line OFFSET MESSAGE: true when a line after line OFFSET of
# ${LOG} ends with MESSAGE. The wrapper prefixes each line with a timestamp;
# matching the end keeps 10.0.0.1 from matching a line about 10.0.0.10.
log_has_new_line() {
    docker exec "${TARGET}" tail -n "+$(( $1 + 1 ))" "${LOG}" 2>/dev/null \
        | awk -v msg="$2" '
            length($0) >= length(msg) && substr($0, length($0) - length(msg) + 1) == msg { found = 1 }
            END { exit !found }
        '
}

ar_payload() {
    local cmd="$1"
    local srcip="$2"
    cat <<EOF
{"version":1,"command":"${cmd}","parameters":{"extra_args":[],"alert":{"data":{"srcip":"${srcip}"}},"program":"firewall-drop"}}
EOF
}

# --- step 1: kali srcip on `add` -- expect short-circuit + log entry --------
log "step 1: AR add with srcip=${KALI_IP} (kali, whitelisted) — expect skip"
PAYLOAD=$(ar_payload add "${KALI_IP}")
offset1=$(log_line_count)
docker exec -i "${TARGET}" \
    env APTL_AR_IPTABLES=/bin/false "${WRAPPER}" <<<"${PAYLOAD}" \
    && rc1=0 || rc1=$?
if [ "${rc1}" -ne 0 ]; then
    fail "wrapper exited ${rc1} for whitelisted ${KALI_IP}; expected 0 (short-circuit, no iptables)"
fi
pass "wrapper short-circuited on whitelisted ${KALI_IP}"

# Verify the log entry among the lines this step appended only: the log
# keeps every earlier run's lines, which would otherwise satisfy the check.
if ! log_has_new_line "${offset1}" "SKIPPED for whitelisted ${KALI_IP}"; then
    fail "no 'SKIPPED for whitelisted ${KALI_IP}' line in ${LOG} on ${TARGET}"
fi
pass "log entry present in ${LOG}"

# --- step 2: attacker srcip on `add` -- expect iptables call (rc!=0 with /bin/false)
log "step 2: AR add with srcip=${ATTACKER_IP} (non-whitelisted) — expect iptables call"
PAYLOAD=$(ar_payload add "${ATTACKER_IP}")
docker exec -i "${TARGET}" \
    env APTL_AR_IPTABLES=/bin/false "${WRAPPER}" <<<"${PAYLOAD}" \
    && rc2=0 || rc2=$?
if [ "${rc2}" -eq 0 ]; then
    fail "wrapper exited 0 for non-whitelisted ${ATTACKER_IP}; expected non-zero (mock iptables=/bin/false makes -I fail)"
fi
pass "wrapper invoked iptables for non-whitelisted ${ATTACKER_IP} (rc=${rc2})"

# --- step 3: kali srcip on `delete` -- delete branch must run unconditionally
log "step 3: AR delete with srcip=${KALI_IP} — expect delete branch to run (cleanup unconditional)"
PAYLOAD=$(ar_payload delete "${KALI_IP}")
offset3=$(log_line_count)
docker exec -i "${TARGET}" \
    env APTL_AR_IPTABLES=/bin/false "${WRAPPER}" <<<"${PAYLOAD}" \
    && rc3=0 || rc3=$?
# With /bin/false, iptables -C returns 1 (rule not present), wrapper
# exits 0 and logs 'removed 0 DROP rule(s)'. The CRITICAL check: did
# we hit the delete branch (proves the whitelist didn't short-circuit)?
if ! log_has_new_line "${offset3}" " DROP rule(s) for ${KALI_IP}"; then
    fail "no 'removed N DROP rule(s) for ${KALI_IP}' line in ${LOG}; wrapper short-circuited on delete (cleanup must always run)"
fi
pass "wrapper ran delete branch for ${KALI_IP} (rc=${rc3})"

log "all checks PASS — kali whitelist carve-out is wired correctly on ${TARGET}"
