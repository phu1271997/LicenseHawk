// Deploy LicenseHawk to GenLayer studionet with genlayer-js.
//
// Usage (from the repo root):
//   source ~/.genlayer/env.sh        # exports GENLAYER_PRIVATE_KEY
//   cd frontend                      # so genlayer-js resolves
//   node ../scripts/deploy.mjs
//
// Reads the deployer key from GENLAYER_PRIVATE_KEY (studionet wallet, funded
// from the Studio Accounts panel). Deploys contracts/license_hawk.py and prints
// the new contract address. Paste that address into frontend/src/config.js
// (or set VITE_CONTRACT_ADDRESS in the Vercel build env) and into the README.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CONTRACT_PATH = resolve(__dirname, "../contracts/license_hawk.py");

const PK = process.env.GENLAYER_PRIVATE_KEY;
if (!PK) {
  console.error("Set GENLAYER_PRIVATE_KEY first:  source ~/.genlayer/env.sh");
  process.exit(1);
}

const code = readFileSync(CONTRACT_PATH, "utf8");
const normPk = PK.startsWith("0x") ? PK : "0x" + PK;
const account = createAccount(normPk);
const client = createClient({ chain: studionet, account });

console.log("Deployer:", account.address);
console.log("Contract:", CONTRACT_PATH, `(${code.length} bytes)`);

const hash = await client.deployContract({ code, args: [] });
console.log("Deploy tx:", hash);

const receipt = await client.waitForTransactionReceipt({
  hash,
  status: "FINALIZED",
  retries: 120,
  interval: 10000,
});

// The deployed address lands in different spots across builds; probe them all.
const addr =
  receipt?.data?.contract_address ||
  receipt?.contract_address ||
  receipt?.data?.contractAddress ||
  receipt?.contractAddress ||
  (receipt?.data && receipt.data["contract_address"]);

console.log("Status:", receipt?.status || receipt?.statusName || "(unknown)");
if (addr) {
  console.log("\n==> NEW CONTRACT ADDRESS:", addr, "\n");
} else {
  console.log("\nCould not auto-extract the address. Full receipt:\n");
  console.log(JSON.stringify(receipt, null, 2));
}
