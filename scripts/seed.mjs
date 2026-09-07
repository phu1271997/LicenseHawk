// Seed three demo cases on studionet so the Explorer catalog opens onto a
// docket with visible on-chain rulings from the moment the listing lands.
//
// Usage (from frontend/ so genlayer-js resolves):
//   cd frontend
//   cp ../scripts/seed.mjs ./seed-run.mjs
//   export LICENSE_HAWK_PRIVATE_KEY=0x<a funded studionet key>
//   export VITE_CONTRACT_ADDRESS=0x<deployed license_hawk contract>
//   node seed-run.mjs
//   rm seed-run.mjs
//
// Each case is driven through file_case -> respond_case -> adjudicate ->
// enforce and left in CASE_ENFORCED state. The script is idempotent:
// re-running skips case ids already in CASE_ENFORCED.
//
// Rate-limited: paces itself under studionet's 30 req/min public RPC cap
// with a 10s poll interval on receipts and exponential backoff on -32029
// rate-limit errors.
//
// Requires roughly 8 GEN in the funder wallet: three cases posting
// ~2 GEN of bonds each, plus gas, split between claimant and respondent.
// The respondent side signs from a disposable keypair derived per case;
// note that in real usage the actual respondent would post their own bond.
// For the seed we simulate both parties from the same funder for
// simplicity — the tribunal ruling still validates end-to-end because
// the LLM sees the codebases, not the wallets.

import { createClient, createAccount } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const CONTRACT = process.env.VITE_CONTRACT_ADDRESS;
const PK = process.env.LICENSE_HAWK_PRIVATE_KEY;
if (!CONTRACT || !PK){
  console.error("Set VITE_CONTRACT_ADDRESS and LICENSE_HAWK_PRIVATE_KEY first.");
  process.exit(1);
}

const REPO_RAW = "https://raw.githubusercontent.com/phu1271997/LicenseHawk/main/docs/samples/evidence";

const funder = createAccount(PK);
const client = createClient({ chain: studionet, account: funder });
console.log("Funder (also acts as claimant):", funder.address);

const CASES = [
  {
    label: "Infringement confirmed — GPL-3.0 code shipped in a closed product",
    license: "GPL-3.0",
    source: `${REPO_RAW}/case0_source.txt`,
    target: `${REPO_RAW}/case0_target.txt`,
    claim_notes:
      "Target ships libtinyparse verbatim inside a proprietary SaaS binary with no NOTICE, no LICENSE, and no corresponding source disclosure. §5 of GPL-3.0 is unmet.",
    defense_urls: [
      { url: `${REPO_RAW}/case0_defense.txt`, note: "Respondent's admission and legal theory." },
    ],
    defense_notes: "Respondent admits verbatim copying and argues SaaS distribution is not covered by GPL-3.0.",
    bond: 1_000_000n,
  },
  {
    label: "No infringement — MIT attribution is present in NOTICE",
    license: "MIT",
    source: `${REPO_RAW}/case1_source.txt`,
    target: `${REPO_RAW}/case1_target.txt`,
    claim_notes:
      "Target includes our kingfisher-color palette functions verbatim; we believe attribution is missing.",
    defense_urls: [
      { url: `${REPO_RAW}/case1_defense.txt`, note: "Our NOTICE file with the MIT text and copyright preserved." },
    ],
    defense_notes: "MIT text and Kingfisher Studio copyright are reproduced verbatim in our NOTICE file, shipped alongside the binary and viewable in the app's About screen.",
    bond: 1_000_000n,
  },
  {
    label: "Retaliatory claim — target predates the claimant's release by six years",
    license: "Apache-2.0",
    source: `${REPO_RAW}/case2_source.txt`,
    target: `${REPO_RAW}/case2_target.txt`,
    claim_notes:
      "Target ships stat helpers substantially similar to microstats v3.0.0; attribution and NOTICE are missing.",
    defense_urls: [
      { url: `${REPO_RAW}/case2_defense.txt`, note: "Git history shows our file predates microstats by six years." },
    ],
    defense_notes: "Our bearing_math.py file has existed since March 2019, six years before the microstats v3.0.0 release. The implementations are textbook one-liners not owed to the claimant.",
    bond: 1_500_000n,
  },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function rpc(label, fn, maxRetries = 30){
  for (let attempt = 0; attempt < maxRetries; attempt++){
    try { return await fn(); }
    catch (e){
      const msg = String(e?.details || e?.cause?.message || e?.message || e);
      const retryAfter = e?.cause?.data?.retry_after_seconds;
      if (/rate limit/i.test(msg) || /-32029/.test(msg)){
        const wait = ((retryAfter ?? 5) + 3) * 1000;
        console.log(`     ${label} rate-limited, waiting ${wait / 1000}s (retry ${attempt + 1}/${maxRetries})…`);
        await sleep(wait);
        continue;
      }
      throw e;
    }
  }
  throw new Error(`Gave up on ${label} after rate-limit retries`);
}

async function readTotal(){
  return Number(await rpc("get_total_cases", () =>
    client.readContract({ address: CONTRACT, functionName: "get_total_cases", args: [] })
  ));
}

async function readCase(id){
  try {
    const raw = await rpc(`get_case(${id})`, () =>
      client.readContract({ address: CONTRACT, functionName: "get_case", args: [String(id)] })
    );
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (e){
    const blob = JSON.stringify(e?.cause?.data?.receipt?.genvm_result || {}) + " " + (e?.message || "");
    if (/Case not found|not found/i.test(blob)) return null;
    throw e;
  }
}

async function readCaseIfExists(id){
  const total = await readTotal();
  if (id >= total) return null;
  return readCase(id);
}

async function writeAndWait(label, fn, args, value = 0n, signer = client){
  console.log(`     tx ${label}…`);
  const hash = await rpc(`write ${label}`, () =>
    signer.writeContract({ address: CONTRACT, functionName: fn, args, value })
  );
  console.log(`     hash: ${hash}`);
  await rpc(`wait ${label}`, () =>
    signer.waitForTransactionReceipt({
      hash, status: "FINALIZED", retries: 60, interval: 10000,
    })
  );
  await sleep(4000);
  return hash;
}

const startTotal = await readTotal();
console.log("Initial next_id / total cases:", startTotal);

for (let i = 0; i < CASES.length; i++){
  const C = CASES[i];
  const caseId = startTotal + i;
  console.log(`\n── Case ${caseId} — ${C.label}`);

  let existing = await readCaseIfExists(caseId);
  if (existing && existing.status === "CASE_ENFORCED"){
    console.log(`   already ${existing.status} — skipping.`);
    continue;
  }

  // A per-case disposable respondent key. In real usage the actual accused
  // party would sign; for the seed we derive one respondent per case and
  // sign both sides from the funder's balance.
  const respondentAcct = createAccount();
  const respondentClient = createClient({ chain: studionet, account: respondentAcct });
  console.log("   respondent (disposable):", respondentAcct.address);

  if (!existing){
    await writeAndWait(
      "file_case",
      "file_case",
      [respondentAcct.address, C.source, C.target, C.license, C.claim_notes],
      C.bond,
    );
    existing = await readCase(caseId);
    if (!existing){
      console.log("   case not yet visible; sleeping 10s…");
      await sleep(10000);
      existing = await readCase(caseId);
    }
    if (!existing) throw new Error(`Case ${caseId} never appeared on chain`);
  } else {
    console.log(`   case exists, status: ${existing.status}`);
  }

  if (existing.status === "CASE_FILED"){
    // Fund the disposable respondent so it can post its own bond + gas.
    console.log("   funding respondent for their bond…");
    const fundHash = await rpc("fund respondent", () =>
      client.sendTransaction({
        to: respondentAcct.address,
        value: C.bond + 100_000n,
      })
    );
    console.log(`     funding hash: ${fundHash}`);
    await rpc("wait fund respondent", () =>
      client.waitForTransactionReceipt({
        hash: fundHash, status: "FINALIZED", retries: 60, interval: 10000,
      })
    );

    await writeAndWait(
      "respond_case",
      "respond_case",
      [String(caseId), JSON.stringify(C.defense_urls), C.defense_notes],
      C.bond,
      respondentClient,
    );
    existing = await readCase(caseId);
  }

  if (existing.status === "CASE_CONTESTED"){
    console.log("   Adjudicate — AI tribunal may take 1–3 minutes…");
    await writeAndWait("adjudicate", "adjudicate", [String(caseId)]);
    existing = await readCase(caseId);
  }

  if (existing.status === "CASE_ADJUDICATED"){
    await writeAndWait("enforce", "enforce", [String(caseId)]);
    existing = await readCase(caseId);
  }

  console.log(`   status: ${existing.status}`);
  console.log(`   verdict: ${existing.verdict}  remedy: ${existing.remedy}`);
  console.log(`   payouts: claimant=${existing.payout_claimant} respondent=${existing.payout_respondent}`);
  console.log(`   reason: ${(existing.reason || "").slice(0, 240)}`);
}

console.log(`\nDone. Explorer: https://explorer-studio.genlayer.com/address/${CONTRACT}`);
