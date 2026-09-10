// Live end-to-end test of the cancellation path on the deployed studionet
// contract. Files a case, then cancels it as the claimant, and asserts the
// case ends in CASE_CANCELLED with the full claimant bond refunded.
//
// Usage (from frontend/, so genlayer-js resolves):
//   source ~/.genlayer/env.sh
//   VITE_CONTRACT_ADDRESS=0x... node test_cancel_live.mjs
//
// Run only when the seed is NOT running (shared funder key → nonce conflicts).

import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const CONTRACT = process.env.VITE_CONTRACT_ADDRESS;
const PK = "0x" + process.env.GENLAYER_PRIVATE_KEY.replace(/^0x/, "");
const BOND = 1_000_000n;

const account = createAccount(PK);
const client = createClient({ chain: studionet, account });
const respondent = createAccount(); // never funded, never responds

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function rpc(label, fn) {
  for (let i = 0; i < 30; i++) {
    try { return await fn(); }
    catch (e) {
      const msg = String(e?.details || e?.cause?.message || e?.message || e);
      if (/rate limit/i.test(msg) || /-32029/.test(msg)) {
        const wait = ((e?.cause?.data?.retry_after_seconds ?? 5) + 3) * 1000;
        console.log(`  ${label} rate-limited, waiting ${wait / 1000}s…`);
        await sleep(wait); continue;
      }
      throw e;
    }
  }
  throw new Error(`gave up on ${label}`);
}

async function write(fn, args, value = 0n) {
  const hash = await rpc(`write ${fn}`, () =>
    client.writeContract({ address: CONTRACT, functionName: fn, args, value }));
  await rpc(`wait ${fn}`, () =>
    client.waitForTransactionReceipt({ hash, status: "FINALIZED", retries: 60, interval: 10000 }));
  await sleep(4000);
  return hash;
}
async function readCase(id) {
  const raw = await rpc(`get_case(${id})`, () =>
    client.readContract({ address: CONTRACT, functionName: "get_case", args: [String(id)] }));
  return typeof raw === "string" ? JSON.parse(raw) : raw;
}

const before = Number(await rpc("total", () =>
  client.readContract({ address: CONTRACT, functionName: "get_total_cases", args: [] })));
const id = before;
console.log("Filing case", id, "then cancelling it. Claimant:", account.address);

await write("file_case", [
  respondent.address,
  "https://raw.githubusercontent.com/phu1271997/LicenseHawk/main/docs/samples/evidence/case0_source.txt",
  "https://raw.githubusercontent.com/phu1271997/LicenseHawk/main/docs/samples/evidence/case0_target.txt",
  "MIT",
  "Unanswered-filing demonstration: respondent never posts a bond.",
], BOND);

let c = await readCase(id);
console.log("  after file:", c.status, "claimant_bond", c.claimant_bond);
if (c.status !== "CASE_FILED") throw new Error("expected CASE_FILED");

await write("cancel_case", [String(id)]);
c = await readCase(id);
console.log("  after cancel:", c.status, "payout_claimant", c.payout_claimant, "payout_respondent", c.payout_respondent);

const ok = c.status === "CASE_CANCELLED"
  && Number(c.payout_claimant) === Number(BOND)
  && Number(c.payout_respondent) === 0;
console.log(ok ? "\nPASS: cancellation refunded the full claimant bond." : "\nFAIL");
process.exit(ok ? 0 : 1);
