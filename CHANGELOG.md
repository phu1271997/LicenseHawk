# Changelog

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
