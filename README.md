# LicenseHawk — Open-Source License Enforcement Tribunal on GenLayer

> An **Intelligent Contract** on GenLayer that turns every open-source license violation claim into an on-chain AI tribunal ruling: validators fetch the claimant's source, fetch the alleged infringer's source, re-read the license, and issue a verdict with a remedy. Bonds are distributed accordingly.

- **Live app:** `TO_BE_FILLED_AFTER_DEPLOY` (Vercel)
- **Contract:** deployed on **GenLayer Studio Network** (studionet) — address in `frontend/src/config.js`
- **Explorer:** https://explorer-studio.genlayer.com

---

## 1. Problem

Open-source licenses are the constitutional layer of the software industry, and their enforcement is broken. A GPL project embedded inside a closed SaaS, an MIT library shipped without the required attribution notice, an Apache-2.0 fork failing to preserve the NOTICE file — each is a real breach with no fast, neutral, cheap forum to adjudicate. Court is slow and expensive; the SFC handles only a handful of high-profile cases a year; DMCA takedowns are blunt and often ignored. In practice, enforcement runs on the goodwill and legal budget of a small number of maintainers, and most breaches go unchallenged.

## 2. Why LicenseHawk would DIE without GenLayer

The ruling requires three things Solidity cannot do:

1. **Read raw source from the web on-chain** — `gl.nondet.web.render` on both the claimant's and target's code URLs. No oracle, no trusted middleman.
2. **Read and interpret a license text** — matching a specific clause of GPL-3.0 §5, MIT's notice requirement, or Apache-2.0's NOTICE preservation to the concrete facts of the case.
3. **Subjective judgement** — "is this a derivative work?", "is idiomatic code copyrightable?", "did the target already comply?" are legal-style questions a human judge resolves. The LLM at GenLayer's consensus layer turns that judgement into a result the chain can execute on.

Strip out the AI and the web reads, and the project has nothing left — there is no way to grade a licensing dispute with a traditional smart contract.

## 3. Architecture

```
┌─────────────┐   genlayer-js    ┌───────────────────────────┐
│  Frontend   │ ───────────────▶ │  LicenseHawk (Python IC)   │
│  (Vite SPA) │ ◀─────────────── │  on GenLayer studionet     │
└─────────────┘   read state     └────────────┬──────────────┘
                                              │ adjudicate()
                                              ▼
                             ┌───────────────────────────────┐
                             │  AI Tribunal (validators)      │
                             │  • web.render(source_url)      │
                             │  • web.render(target_url)      │
                             │  • web.render(defense_urls)    │
                             │  • LLM: rule on the license    │
                             │  • validator_fn: check MEANING │
                             └───────────────────────────────┘
```

### Case state machine

```
CASE_FILED ──respond_case──▶ CASE_CONTESTED ──adjudicate──▶ CASE_ADJUDICATED
                                                                    │
                                                                    │ enforce
                                                                    ▼
                                                              CASE_ENFORCED
```

### Verdict categories & bond distribution

| Verdict                    | Claimant payout            | Respondent payout         |
|----------------------------|----------------------------|---------------------------|
| `INFRINGEMENT_CONFIRMED`   | own bond + respondent bond | 0                         |
| `NO_INFRINGEMENT`          | 0                          | own bond + claimant bond  |
| `DERIVATIVE_UNCLEAR`       | own bond                   | own bond                  |
| `RETALIATORY_CLAIM`        | 0                          | own bond + claimant bond  |

Both `NO_INFRINGEMENT` and `RETALIATORY_CLAIM` transfer the claimant's bond to the respondent — the distinction is whether the panel treats the filing as merely wrong (a legitimate close call the claimant lost) or as abusive (target predates the claim, code isn't copyrightable, claimant lacks standing). The contract enforces bond conservation at enforcement: `payout_claimant + payout_respondent == claimant_bond + respondent_bond`, always.

### Consensus quality — how axis 2 is earned

`validator_fn` does not check schema shape. It re-fetches the two codebases and the defense URLs, re-runs the LLM, and only agrees when the leader's verdict and its own converge on the same legal outcome. Two rulings that word their `reason` differently but land on the same verdict + remedy consensus; two rulings that split on which party wins do **not**. A one-step tolerance is granted only around `DERIVATIVE_UNCLEAR`: a validator that thinks the case is unclear may still ratify a leader that took a side. Every other pair of verdicts must match exactly. See `contracts/license_hawk.py`, `validator_fn` and `_verdicts_agree`.

## 4. Repository layout

```
LicenseHawk/
├── contracts/
│   └── license_hawk.py         # Main Intelligent Contract
├── sanity/
│   └── storage_test.py         # Probe to deploy first
├── frontend/
│   ├── index.html              # Single-page dApp, legal-brief aesthetic
│   ├── src/config.js           # CONTRACT_ADDRESS + chain
│   ├── public/logo.{svg,png}   # 1024 / 512 / 128 favicon variants
│   └── package.json
├── tests/
│   └── test_license_hawk.py    # gltest: state machine, permissions, bond math
├── scripts/
│   ├── deploy.sh               # localnet / CLI deploy
│   └── seed.mjs                # 3 demo cases through the full lifecycle
├── docs/
│   ├── ARCHITECTURE.md
│   └── samples/evidence/       # 3 source/target/defense triples
├── CHANGELOG.md
├── EXPLORER_SUBMISSION.md
└── README.md
```

## 5. Deploying the contract on studionet

1. Open https://studio.genlayer.com/run-debug
2. **Settings → Reset Storage → Confirm → hard refresh** (Cmd/Ctrl+Shift+R).
3. Deploy `sanity/storage_test.py` first — click the transaction and confirm **Result: SUCCESS**.
4. Deploy `contracts/license_hawk.py` — again verify `Result: SUCCESS` on the tx.
5. Paste the contract address into `frontend/src/config.js` as `CONTRACT_ADDRESS`, or set `VITE_CONTRACT_ADDRESS` in the Vercel build environment.

**Funding the demo wallet:** open Studio → **Accounts** panel → transfer GEN from a pre-funded Studio account to the address you use with MetaMask. studionet has no public faucet; do not use `testnet-faucet.genlayer.foundation` (that funds testnet, a separate network).

## 6. Running the frontend

```bash
cd frontend
npm install
VITE_CONTRACT_ADDRESS=0x<your contract> npm run dev
```

Open the app in a browser with MetaMask installed → **Connect Wallet** (the app will switch or add the GenLayer Studio Network for you) → walk the four tabs: **File Case → Respond → Adjudicate & Enforce → Rulings Index**.

**Vercel deploy**: point the project at the `frontend/` directory, set `VITE_CONTRACT_ADDRESS` and `VITE_CHAIN=studio` as environment variables, and build.

## 7. Seeding demo data

```bash
cd frontend
cp ../scripts/seed.mjs ./seed-run.mjs
export LICENSE_HAWK_PRIVATE_KEY=0x<a funded studionet key>
export VITE_CONTRACT_ADDRESS=0x<contract address>
node seed-run.mjs
rm seed-run.mjs
```

The script drives three cases from `file_case` through `enforce`, using disposable respondent keypairs it funds from the funder wallet. Requires roughly 8 GEN in the funder wallet on studionet. The three seeded cases are deliberately calibrated to produce distinct rulings: `case0` (GPL-3.0 verbatim copy into closed SaaS → INFRINGEMENT_CONFIRMED), `case1` (MIT with attribution present → NO_INFRINGEMENT), `case2` (Apache-2.0 target predates the claim → RETALIATORY_CLAIM or DERIVATIVE_UNCLEAR depending on the tribunal's read).

**Note on the shared funder key:** if a shared studionet key is used for the seed step across multiple projects, run the seed scripts **sequentially, not in parallel**, to avoid nonce conflicts.

## 8. Tests

```bash
gltest tests/test_license_hawk.py
```

Covers the state machine (all four transitions), permissions (only the named respondent may answer; strangers cannot adjudicate), input validation (zero bond, self-filing, unknown license, missing defense URLs), and the bond-conservation invariant after enforcement. The integration test mocks the LLM + web to exercise the full happy path.

## 9. Further reading

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data model, consensus design, verdict-to-remedy consistency, sequence diagrams.
- [`docs/samples/evidence/`](docs/samples/evidence/) — the three worked source / target / defense triples used by the seed script.
- [`EXPLORER_SUBMISSION.md`](EXPLORER_SUBMISSION.md) — Portal Explorer draft with verified character counts.

---

## Peter's next 3 steps

1. **Deploy the contract on Studio.** Open `contracts/license_hawk.py` in Studio, deploy on studionet, verify `Result: SUCCESS`. Copy the address.
2. **Paste the address into `frontend/src/config.js`** (or set `VITE_CONTRACT_ADDRESS` on Vercel and redeploy).
3. **Run the seed** (see §7). Requires ~8 GEN in the funder wallet on studionet.

## GitHub / Vercel fallback commands

If `gh` or `vercel` are not authed in this session, run them yourself:

```bash
# GitHub
cd /Users/peter/Downloads/AI/Genlayer/14-LicenseHawk
gh repo create phu1271997/LicenseHawk --public --source=. --push

# Vercel
cd /Users/peter/Downloads/AI/Genlayer/14-LicenseHawk/frontend
npm install
npm run build
vercel link --project license-hawk --yes
vercel deploy --prod --yes
vercel alias set <deployment-url> license-hawk.vercel.app
```

---

*LicenseHawk is deployed on **GenLayer Studio Network (studionet)** — a Preview environment. GenLayer is in the testnet stage; network details may change — cross-check at docs.genlayer.com before redeploying.*
