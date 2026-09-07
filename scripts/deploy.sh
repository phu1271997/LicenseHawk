#!/usr/bin/env bash
# Deploy LicenseHawk.
#
# The primary deploy target for this project is Studio (studionet). Use the
# Studio UI at https://studio.genlayer.com/run-debug to deploy — see the
# README for the full step-by-step. This script is for the localnet loop
# and anyone who later wants to target testnet with the CLI.
#
# Prerequisites:
#   1. npm install -g genlayer
#   2. genlayer keygen  (or import an existing key)
#
# Recommended order:
#   1. Deploy sanity/storage_test.py first to confirm the environment.
#   2. Then deploy contracts/license_hawk.py.

set -euo pipefail

NETWORK="${1:-localnet}"

echo "==> Deploying sanity contract first (sanity/storage_test.py)"
genlayer deploy \
  --contract sanity/storage_test.py \
  --network "$NETWORK"

echo ""
echo "==> Sanity OK. Deploying main contract (contracts/license_hawk.py)"
genlayer deploy \
  --contract contracts/license_hawk.py \
  --network "$NETWORK"

echo ""
echo "==> Done. Copy the address into frontend/src/config.js (or set VITE_CONTRACT_ADDRESS in the build env)."
