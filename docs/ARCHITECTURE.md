# LicenseHawk — Architecture

## 1. Contract data model

```python
@allow_storage
@dataclass
class Case:
    claimant: Address
    respondent: Address
    license_type: str          # SPDX id, one of LICENSE_FAMILIES
    source_url: str            # claimant's own source
    target_url: str            # allegedly infringing product
    claim_notes: str
    defense_urls_json: str     # JSON string of [{"url","note"}, ...]
    defense_notes: str
    claimant_bond: bigint
    respondent_bond: bigint
    status: str                # CASE_FILED | CASE_CONTESTED | CASE_ADJUDICATED | CASE_ENFORCED
    verdict: str               # populated by adjudicate()
    remedy: str
    similarity_signal: str
    attribution_status: str
    license_analysis: str
    reason: str
    payout_claimant: bigint    # populated by enforce()
    payout_respondent: bigint
```

The `cases` map is `TreeMap[str, Case]` — every case id crosses the calldata boundary of `get_case`, so string keys are mandatory (see R19 in `02-common-errors.md`).

**Why evidence URL lists are JSON strings inside the dataclass:** constructing a `DynArray[T]` from inside a `@dataclass __init__` is disallowed on this Studio build — `TypeError: _GenericAlias.__init__() missing args`. The v1 attempt cost us a full redeploy on the sister RentArbiter project. JSON strings keep the contract deployable while preserving the same semantics.

## 2. Lifecycle

```
                    claimant posts bond
                          │
                          ▼
      ┌───────────────────────────────────────┐
      │            CASE_FILED                 │
      │  claimant_bond > 0, respondent_bond=0 │
      └────────────────┬──────────────────────┘
                       │ respondent posts bond + defense URLs
                       ▼
      ┌───────────────────────────────────────┐
      │           CASE_CONTESTED              │
      │  both bonds posted, awaiting tribunal │
      └────────────────┬──────────────────────┘
                       │ adjudicate() — AI tribunal ruling
                       ▼
      ┌───────────────────────────────────────┐
      │           CASE_ADJUDICATED            │
      │  verdict + remedy + analysis on-chain │
      └────────────────┬──────────────────────┘
                       │ enforce()
                       ▼
      ┌───────────────────────────────────────┐
      │             CASE_ENFORCED             │
      │  bonds distributed, case closed       │
      └───────────────────────────────────────┘
```

Any call out of order is rejected. `enforce` is idempotent-by-refusal: once a case is `CASE_ENFORCED`, a second call reverts on the state guard.

## 3. Nondeterministic block

### API choice

We use `gl.vm.run_nondet(leader_fn, validator_fn)` with a hand-written validator rather than `gl.eq_principle.prompt_comparative`. Reasons:

1. **Consistency invariants**. The remedy must be consistent with the verdict (`INFRINGEMENT_CONFIRMED` → an action; every other verdict → `REMEDY_NONE`). A free-text comparator cannot enforce that structural rule.
2. **License-analysis grounding**. The leader's `license_analysis` field must at least mention the license family (either the full SPDX id or the family prefix). A validator that sees generic legalese with no reference to the license in force rejects the ruling. This blocks the failure mode where the LLM writes a plausible-sounding but off-topic analysis.
3. **One-step tolerance around UNCLEAR**. A hand-written validator can encode exactly which verdict pairs count as agreement. We allow `INFRINGEMENT_CONFIRMED ↔ DERIVATIVE_UNCLEAR` and `NO_INFRINGEMENT ↔ DERIVATIVE_UNCLEAR` (a validator that thinks the case is unclear may still ratify a leader who took a side). Everything else must match exactly. `prompt_comparative` cannot express that asymmetry.

If a future SDK build only exposes `run_nondet_unsafe`, the code falls back cleanly — the validator body is unchanged. That is noted in a comment above the call.

### Prompt

The leader prompt is a four-step ruling framework:

1. Is there a derivative work at all? (substantial similarity, not idiomatic patterns.)
2. If yes, what does the governing clause of the license require? (GPL/AGPL: source disclosure; MIT/BSD/Apache: notice preservation; LGPL: dynamic-link allowances.)
3. Has the target satisfied that requirement?
4. Is the claim itself abusive? (target predates the claim, code is not copyrightable, claimant lacks standing.)

The LLM is required to return a JSON object with exactly six keys, and the leader is instructed to cite a specific clause of the license in force. The validator parses and re-runs.

### Nondet safety

- Storage is read **before** the block and captured through closure. No `self.` access inside `leader_fn` / `validator_fn`.
- Defense URLs are capped at 5 per call to keep the nondet round bounded.
- Every `web.render` call is wrapped in `try/except`; an unreachable URL becomes `[UNREACHABLE: ...]` text in the prompt so the tribunal can reason about missing evidence rather than crashing.

## 4. Bond math

Bond conservation is enforced twice:

1. Inside `enforce()`, immediately after computing `pay_claimant` and `pay_respondent`, we assert `pay_claimant + pay_respondent == claimant_bond + respondent_bond`.
2. Native GEN transfers only happen after the state is written; no `emit_transfer` is issued for a zero-amount payout (a zero transfer would waste a call and is not the intent).

For `INFRINGEMENT_CONFIRMED` the claimant receives the entire pool as remedy (they recover their own bond and take the respondent's bond). For `NO_INFRINGEMENT` and `RETALIATORY_CLAIM` the respondent receives the entire pool. For `DERIVATIVE_UNCLEAR` each side gets exactly their own bond back. Total pool is always preserved.

## 5. Threat model & edge cases

| Case                                        | Handling                                                                                     |
|---------------------------------------------|----------------------------------------------------------------------------------------------|
| Zero bond                                   | Reverted on `file_case` and `respond_case` — `Bond must be greater than zero`.               |
| Self-filing (claimant == respondent)        | Reverted on `file_case`.                                                                     |
| Unsupported license family                  | Reverted on `file_case` — the LLM has no canonical text to reason about.                     |
| Respondent bond by a non-respondent         | Reverted — only `case.respondent` may answer.                                                |
| Empty defense URLs                          | Reverted — a defense of zero URLs would leave the tribunal only the claim to read.           |
| Adjudicate before response                  | Reverted on state guard.                                                                     |
| `web.render` fail on any URL                | Substituted with `[UNREACHABLE]` in the prompt; tribunal reasons about the missing evidence. |
| LLM returns unknown verdict / remedy        | `run_nondet` never returns; `validator_fn` disagrees, consensus stalls, tx reverts.          |
| Leader returns inconsistent verdict+remedy  | Validator rejects; also asserted again post-consensus in `adjudicate`.                       |
| Enforce called twice                        | State guard on second call — `Case must be ADJUDICATED before enforcement`.                  |

## 6. Explorer view surface

Two views are safe to call without a wallet:

- `get_total_cases() -> int` — used by the Rulings Index to page the docket.
- `get_case(case_id: str) -> str` — returns a JSON blob of the entire case for rendering an opinion card.
- `get_supported_licenses() -> str` — JSON array of SPDX identifiers the contract recognises.

Views return `str` (JSON dump) rather than complex dataclasses because the calldata format only supports scalars, `str`, `bytes`, and JSON-compatible mappings; returning a `Case` directly would fail schema generation.
