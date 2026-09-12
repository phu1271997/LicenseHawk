# GENLAYER PROJECT EXPLORER — LicenseHawk Submission Draft
**Project:** LicenseHawk · **Prepared:** 2026-09-07 · **Status:** DO NOT SUBMIT YET (contract must be deployed and 3 demo cases seeded first)

## Pre-submit gate status

- Contract source ready: `contracts/license_hawk.py`.
- Live frontend ready: single-page Vite dApp, MetaMask auto-switch, wallet-less read on Rulings Index tab.
- Sample evidence for three distinct verdicts committed to `docs/samples/evidence/` and reachable via `raw.githubusercontent.com`.
- **Blocking before Submit** (Peter):
  1. Deploy `contracts/license_hawk.py` on Studio (studionet). Confirm `Result: SUCCESS`.
  2. Paste the address into `frontend/src/config.js` (or `VITE_CONTRACT_ADDRESS` on Vercel) and redeploy.
  3. Run `scripts/seed.mjs` so three RESOLVED cases exist for the reviewer.
  4. Open `https://explorer-studio.genlayer.com/address/<CONTRACT>` in a browser and confirm you see `adjudicate` transactions with `GENVM RESULT: SUCCESS` and `CONSENSUS RESULT: Accepted`.

---

## Project name
**LicenseHawk**

## Primary category
**Dispute Resolution**

*Rationale:* GenLayer positions itself as the "adjudication layer" and LicenseHawk is a literal adjudication use case — two parties disagree over whether a license was breached, an AI tribunal issues a binding verdict, the contract distributes bonds. Chose this over `AI & Agents` deliberately: nearly every project in the shuffled catalog is AI-powered, so that label would not differentiate and would sink the listing.

## Category tags

- **Tag 1 — License Claims** *(the tag the project was built to embody)*
  Implemented by the whole contract — `file_case(license_type, source_url, target_url, ...)` records the license in force; `adjudicate()` re-reads the license text inside the leader prompt and requires the license family to appear in the returned analysis; the validator rejects rulings whose `license_analysis` does not mention the license. See `contracts/license_hawk.py`, `_license_reference` and `validator_fn`.

- **Tag 2 — Evidence Assessment** *(what happens between filing and ruling)*
  Implemented inside `adjudicate()`. The leader function iterates over the claimant source URL, the target URL, and every defense URL in the case's `defense_urls_json` list, calls `gl.nondet.web.render(url, mode="text")` on each, and feeds the rendered text into the LLM prompt. The verdict is grounded in what the tribunal actually read, not in the parties' assertions.

*Rejected:* `Moderation Appeals` (no takedown mechanic), `Escrow Claims` (bonds are legal-remedy stakes, not escrow of a work-in-progress deliverable), `Appeal Review` (single-round adjudication; a real second-instance review would require a distinct `appeal()` method that we chose not to ship in v0.1), `Jury Selection` (the app calls its tribunal an "AI Tribunal" but validators are chosen by GenLayer, not by LicenseHawk — using that tag would misrepresent the mechanism).

## Logo
`frontend/public/logo.png` — 512×512 PNG (268 KB). Balance scale over a stylized diff hunk with `+` / `-` markers, framed by a courthouse seal ring. High-contrast oxblood on cream, reads at 128 px (verified). 1024 (948 KB) and 128 (24 KB) variants also committed. SVG source at `frontend/public/logo.svg`.

## One-liner (130 / 180)
On-chain AI tribunal for open-source license claims: validators fetch both codebases, re-read the license, and rule with a remedy.

## Description (993 / 1000)
LicenseHawk turns every open-source license violation claim into an on-chain tribunal ruling.

A rightsholder files a case naming their upstream repo, the alleged infringer, the SPDX license, and a bond. The respondent answers with a matching bond and defense URLs. On adjudicate, validators fetch both codebases and each defense URL, re-read the license, and rule. Consensus is on the verdict's meaning — outcome and remedy — not the wording.

Four verdicts: INFRINGEMENT_CONFIRMED, DERIVATIVE_UNCLEAR, NO_INFRINGEMENT, RETALIATORY_CLAIM. On enforce, bonds move per verdict: an infringer forfeits its bond to the claimant; a cleared respondent takes the claimant bond; an unclear case returns each bond.

For OSS maintainers whose GPL, MIT, or Apache code is shipped in violation with no fast, neutral forum today.

Solidity cannot fetch source from GitHub, read a license, or judge derivative work. The ruling lives in unstructured web content and legal reading — GenLayer's home turf.

## How to try it

**Prerequisites**
- MetaMask installed. The app switches / adds the GenLayer Studio Network for you on connect (chainId 61999 / 0xF1EF).
- Roughly 2.5 GEN on your MetaMask address on studionet if you want to file a new case (a ~1 GEN bond plus gas). Fund from Studio → Accounts panel (https://studio.genlayer.com) — studionet has no public faucet.
- No wallet needed to browse the Rulings Index tab.

**Step 1 — Browse existing rulings (no wallet).**
Open the app → click the **Rulings Index** tab → **Refresh Index**. Three seeded cases appear: one INFRINGEMENT_CONFIRMED (a GPL-3.0 parser copied into closed SaaS), one NO_INFRINGEMENT (an MIT library with attribution present), one RETALIATORY_CLAIM (an Apache-2.0 target predating the claimant by six years). Click any row to open its full opinion, including the license analysis, remedy, both bonds, and evidence links.

**Step 2 — Connect a wallet.**
Click **Connect Wallet** (top right). Approve in MetaMask; the app auto-switches to the GenLayer Studio Network. Your address appears next to the button.

**Step 3 — File a new case as the claimant.**
Go to **File Case**. Paste any address you don't control as the respondent. Choose a license (e.g. MIT). Post a bond (e.g. `1000000`). Paste any two public raw URLs as the claimant source and the alleged target. Add claim notes citing the clause. Click **Post Bond & File Case**.

**Step 4 — Answer as the respondent, then request the tribunal.**
Switch MetaMask to the respondent account (or ask the respondent to). Go to **Respond**, enter the case id, paste a JSON array of at least one defense URL, post a matching bond. Switch to **Adjudicate & Enforce**, enter the case id, and click **Request Adjudication**. Wait 1–2 minutes for consensus.

**Step 5 — Read the ruling and enforce it.**
Open **Rulings Index** → refresh → click your new case. The opinion card shows the verdict, remedy, license analysis, and reason. Back on Adjudicate & Enforce, click **Enforce Ruling** — the bonds are distributed. The opinion card updates to CASE_ENFORCED with payouts shown.

**Expected end state:** a new case appears at the top of Rulings Index with status **CASE_ENFORCED**, a verdict badge, a license-analysis paragraph citing a specific clause, and `payout_claimant + payout_respondent` summing to the total bond pool.

**If something goes wrong**
- "MetaMask required" — install MetaMask and reload.
- `insufficient funds` — the connected address has no GEN on studionet. Fund from Studio Accounts.
- Adjudication stuck > 3 minutes — refresh the Rulings tab; sometimes the tx finalized but the button state stuck.

## Expected verification outcome (469 / 500)
Rulings Index shows the seeded ENFORCED cases across distinct verdicts: INFRINGEMENT_CONFIRMED (claimant takes the pool), NO_INFRINGEMENT (respondent takes the pool), and RETALIATORY_CLAIM / DERIVATIVE_UNCLEAR (respondent takes both bonds, or each bond returned). Each opinion cites a specific license clause and payout_claimant + payout_respondent equals the total bond pool. Explorer shows adjudicate + enforce transactions with GENVM RESULT: SUCCESS and CONSENSUS RESULT: Accepted.

## Contract link
`https://explorer-studio.genlayer.com/address/0x174A19cF404751Ccd829cA77DA11ebD577f1B971`

- **Address:** `0x174A19cF404751Ccd829cA77DA11ebD577f1B971`
- **Network:** studionet (GenLayer Studio hosted)
- **Status:** **Preview** (studionet ≠ testnet)
- **Verify before submit:** open the Explorer link in a real browser and confirm at least one `adjudicate` transaction with `Result: SUCCESS` and `Consensus: Accepted`.

## Website
https://license-hawk-tribunal.vercel.app

## GitHub
`https://github.com/phu1271997/LicenseHawk`

## Community links (optional)
Leave blank — no official channels tied to this project.

---

## FINAL CHECKLIST (tick before Submit)

**Truthfulness**
- [ ] Every feature in the description works on the live app right now
- [ ] No mention of a feature not yet built
- [ ] Status **Preview** matches studionet
- [ ] Each tag maps to a real function (see the tags section above)

**Deploy state**
- [ ] Contract deployed on studionet, `Result: SUCCESS` on tx
- [ ] Address pasted into `frontend/src/config.js` (or `VITE_CONTRACT_ADDRESS`)
- [ ] Vercel finished the build with the new address
- [ ] `gen_getContractSchema` returns the eight public methods (file_case, respond_case, cancel_case, adjudicate, enforce, get_case, get_total_cases, get_supported_licenses)
- [ ] Explorer address page opens in a browser and shows `adjudicate` tx with SUCCESS / Accepted

**End-to-end (do it, don't imagine it)**
- [ ] Seeded: 1 INFRINGEMENT_CONFIRMED, 1 NO_INFRINGEMENT, 1 RETALIATORY_CLAIM — visible in incognito without wallet
- [ ] Full path walked with a fresh MetaMask account: connect → file → respond → adjudicate → enforce → opinion shows

**Assets & limits**
- [x] Logo: `frontend/public/logo.png` (PNG, 512×512, 268 KB, verified at 128 px)
- [x] One-liner: 130 chars (limit 180)
- [x] Description: 993 chars (limit 1000)
- [x] Expected verification outcome: 459 chars (limit 500)
- [x] GitHub URL provided (satisfies the "Website or GitHub required" rule)

**Consequences understood**
- [x] Changes requested = one fix pass, 14 days
- [x] Declined = no self-service resubmit
- [x] 1 Projects contribution = 1 Explorer entry — LicenseHawk is that one
