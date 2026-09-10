# Changelog

## 2026-09-10 — v0.2.0 — adjudication & escrow hardening (judge feedback)

Addresses reviewer feedback: "Validator exceptions, malformed rulings, and
unclear outcomes must not approve a decisive payout; the respondent bond must
match the claimant bond; and unanswered filings need a tested timeout or
cancellation path."

### Contract (`license_hawk.py`)
- **Fail-closed adjudication.** `validator_fn` now returns `False` (disagree)
  on any anomaly it cannot reproduce: a validator exception, an unparseable
  re-run, or a re-run yielding an invalid verdict. Previously these abstained
  by *agreeing*, which could let a decisive payout through on a validator that
  never actually reproduced the ruling. Safety over liveness — a transient
  hiccup reverts the tx and can be retried.
- **Exact verdict agreement.** Removed the one-step tolerance around
  `DERIVATIVE_UNCLEAR`. An unclear reading can now only agree with another
  unclear reading; it never ratifies a decisive `INFRINGEMENT_CONFIRMED` /
  `NO_INFRINGEMENT` / `RETALIATORY_CLAIM` leader.
- **Malformed consensus result guard.** `adjudicate` refuses to settle on a
  non-dict / unparseable consensus payload before touching the state machine.
- **Escrow symmetry.** `respond_case` now requires the respondent bond to
  equal the claimant bond exactly (was: any positive amount).
- **Cancellation path.** New `cancel_case` + `CASE_CANCELLED` state: the
  claimant can withdraw an unanswered filing (still `CASE_FILED`, no respondent
  bond in escrow) and recover the full claimant bond.

### Frontend
- Respond form auto-loads the case and locks the respondent bond to the
  claimant's bond (prevents a mismatched-bond revert).
- New "Withdraw an Unanswered Filing" action (`cancel_case`) and a
  `CASE_CANCELLED` docket status.

### Tests
- Added: respondent-bond-must-equal-claimant-bond (low/high/exact), cancel
  refunds claimant, cancel by non-claimant rejected, cancel-after-response
  rejected.

### Deploy
- `scripts/deploy.mjs` — studionet deploy via genlayer-js.
- Redeployed to studionet at `0x174A19cF404751Ccd829cA77DA11ebD577f1B971`.

## 2026-09-07 — v0.1.0 — initial LicenseHawk build

### Contract
- Intelligent Contract `license_hawk.py`: four-state case lifecycle
  (`CASE_FILED → CASE_CONTESTED → CASE_ADJUDICATED → CASE_ENFORCED`).
- Four verdict categories with a matching remedy taxonomy; consistency
  enforced both inside the validator and post-consensus.
- `gl.vm.run_nondet` with a hand-written validator that re-runs the LLM
  and enforces (a) verdict agreement with one-step tolerance around
  `DERIVATIVE_UNCLEAR`, (b) remedy match when both sides find
  infringement, (c) license family named in the analysis text.
- Bond conservation invariant asserted at enforcement time.
- Evidence lists stored as JSON strings inside the `Case` dataclass to
  work around the SDK's disallowance of `DynArray[T]()` inside
  `@dataclass __init__` (learned the hard way on the sister
  RentArbiter project — one full redeploy each).

### Frontend
- Single-page Vite dApp in IBM Plex Serif on cream `#f7f4ec`, deep
  oxblood `#7a2020` accent.
- Four tabs: File Case, Respond, Adjudicate & Enforce, Rulings Index.
- MetaMask auto-switch/add for the GenLayer Studio Network
  (`0xF1EF` / 61999).
- Wallet-less read on the Rulings Index — visitors can browse the
  docket before connecting.
- Court-seal SVG logo (balance scale over stylized diff hunk with
  `+` and `-` markers), rasterised at 1024 / 512 / 128 (all under 2 MB).

### Tests
- `tests/test_license_hawk.py`: state machine, permissions, input
  validation, and one integration test with mocked LLM + web that
  exercises the full lifecycle and asserts bond conservation.

### Docs
- `README.md`, `docs/ARCHITECTURE.md`, `EXPLORER_SUBMISSION.md`.
- Three worked evidence triples under `docs/samples/evidence/`
  calibrated to elicit distinct rulings from the AI tribunal.

### Scripts
- `scripts/deploy.sh` for CLI / localnet.
- `scripts/seed.mjs` — three demo cases driven through the full
  lifecycle, idempotent (skips already-enforced ids), paced at 10 s
  poll intervals with `-32029` backoff to stay under studionet's
  30 req/min public RPC cap.
