# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

import json
import typing
from dataclasses import dataclass


# =============================================================================
# LicenseHawk - Intelligent Contract for open-source license enforcement.
#
# Concept:
#   A rightsholder (maintainer of a GPL / AGPL / MIT / BSD / Apache project)
#   files a claim against a downstream product allegedly shipping their code
#   in violation of the license. Both sides post a bond. An AI Jury of
#   validators re-fetches BOTH codebases from the raw web, re-reads the
#   canonical license text, weighs derivative-work signal, and rules with a
#   remedy. Bonds are distributed according to the verdict.
#
# Why this needs GenLayer:
#   Solidity cannot fetch raw source code from GitHub, cannot read a license
#   document, and cannot exercise judgement on whether one file is a
#   derivative of another. Every element of this ruling lives in unstructured
#   web content and subjective interpretation of legal terms. Strip out the
#   web reads and the LLM and there is no product left.
#
# Consensus principle (axis 2):
#   Validators must agree on the VERDICT (the legal outcome) and the REMEDY
#   (the enforcement action). Prose reasoning may diverge. A one-step
#   tolerance is granted only around DERIVATIVE_UNCLEAR - a validator that
#   thinks a case is unclear may still agree with an INFRINGEMENT or
#   NO_INFRINGEMENT leader. A validator that CONFIRMS infringement while the
#   leader clears the respondent (or vice versa) MUST disagree.
#
# Storage design (learned from painful redeploys):
#   * Evidence URL lists are persisted as JSON strings inside the Case
#     dataclass, not as DynArray fields - constructing a DynArray[...] from
#     inside a @dataclass __init__ is disallowed by the SDK.
#   * Every monetary field is bigint.
#   * The Case map is keyed by str; case ids cross the calldata boundary.
#   * One gl.Contract subclass, exactly named Contract.
# =============================================================================


# Lifecycle states -----------------------------------------------------------
CASE_FILED = "CASE_FILED"           # Claimant has locked the claimant bond.
CASE_CONTESTED = "CASE_CONTESTED"   # Respondent locked their bond too.
CASE_ADJUDICATED = "CASE_ADJUDICATED"  # AI Jury has ruled, awaiting enforce.
CASE_ENFORCED = "CASE_ENFORCED"     # Bonds distributed, ledger settled.
CASE_CANCELLED = "CASE_CANCELLED"   # Unanswered filing withdrawn; bond refunded.

# Verdicts the AI Jury may return --------------------------------------------
VERDICT_INFRINGEMENT = "INFRINGEMENT_CONFIRMED"
VERDICT_UNCLEAR = "DERIVATIVE_UNCLEAR"
VERDICT_NO_INFRINGEMENT = "NO_INFRINGEMENT"
VERDICT_RETALIATORY = "RETALIATORY_CLAIM"

VALID_VERDICTS = {
    VERDICT_INFRINGEMENT,
    VERDICT_UNCLEAR,
    VERDICT_NO_INFRINGEMENT,
    VERDICT_RETALIATORY,
}

# Remedies the AI Jury may prescribe -----------------------------------------
REMEDY_RELEASE_SOURCE = "RELEASE_SOURCE"
REMEDY_ADD_ATTRIBUTION = "ADD_ATTRIBUTION"
REMEDY_REMOVE_CODE = "REMOVE_CODE"
REMEDY_PAY_DAMAGES = "PAY_DAMAGES"
REMEDY_NONE = "NONE"

VALID_REMEDIES = {
    REMEDY_RELEASE_SOURCE,
    REMEDY_ADD_ATTRIBUTION,
    REMEDY_REMOVE_CODE,
    REMEDY_PAY_DAMAGES,
    REMEDY_NONE,
}

# License families the contract understands ----------------------------------
# These names steer the LLM to the correct canonical text.
LICENSE_FAMILIES = {
    "GPL-2.0", "GPL-3.0",
    "AGPL-3.0",
    "LGPL-2.1", "LGPL-3.0",
    "MIT",
    "BSD-2-Clause", "BSD-3-Clause",
    "Apache-2.0",
    "MPL-2.0",
    "OTHER",
}


@allow_storage
@dataclass
class Case:
    # Parties -----------------------------------------------------------------
    claimant: Address
    respondent: Address

    # Case facts --------------------------------------------------------------
    license_type: str
    source_url: str          # claimant's own source code root URL
    target_url: str          # allegedly-infringing product's source URL
    claim_notes: str

    # Respondent's defense ----------------------------------------------------
    defense_urls_json: str   # JSON string: list of {"url": str, "note": str}
    defense_notes: str

    # Bonds -------------------------------------------------------------------
    claimant_bond: bigint
    respondent_bond: bigint

    # State machine -----------------------------------------------------------
    status: str

    # Verdict block (populated at adjudicate) ---------------------------------
    verdict: str
    remedy: str
    similarity_signal: str
    attribution_status: str
    license_analysis: str
    reason: str

    # Bond distribution (populated at enforce) --------------------------------
    payout_claimant: bigint
    payout_respondent: bigint


def _addr_hex(a: Address) -> str:
    try:
        return a.as_hex
    except Exception:
        return str(a)


class Contract(gl.Contract):
    # str-keyed by case_id (a decimal string) so the map is safe across the
    # calldata boundary of public views.
    cases: TreeMap[str, Case]
    next_id: u256
    owner: Address

    def __init__(self):
        self.next_id = u256(0)
        self.owner = gl.message.sender_address

    # ------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------

    def _require(self, cond: bool, msg: str) -> None:
        if not cond:
            raise Exception(msg)

    def _get_case(self, case_id: str) -> Case:
        if case_id not in self.cases:
            raise Exception("Case not found")
        return self.cases[case_id]

    def _pay(self, recipient: Address, amount: bigint) -> None:
        # Native GEN transfer via the standard emit_transfer pattern. We
        # deliberately do NOT use @gl.evm.contract_interface because that
        # bridge is not available on Studio (studionet).
        if int(amount) > 0:
            gl.get_contract_at(recipient).emit_transfer(value=amount)

    # ------------------------------------------------------------------------
    # 1. file_case  -- claimant opens a case, locks the claimant bond.
    # ------------------------------------------------------------------------

    @gl.public.write.payable
    def file_case(
        self,
        respondent: str,
        source_url: str,
        target_url: str,
        license_type: str,
        claim_notes: str,
    ) -> str:
        bond = bigint(gl.message.value)
        self._require(int(bond) > 0, "Claimant bond must be greater than zero")
        self._require(len(source_url) > 0, "Claimant's source URL is required")
        self._require(len(target_url) > 0, "Allegedly-infringing target URL is required")
        self._require(source_url != target_url, "Source and target URLs must differ")
        self._require(license_type in LICENSE_FAMILIES, "Unsupported license type")

        claimant_addr = gl.message.sender_address
        respondent_addr = Address(respondent)
        self._require(
            respondent_addr != claimant_addr,
            "Claimant and respondent must be different parties",
        )

        case_id_int = int(self.next_id)
        self.next_id = self.next_id + u256(1)
        case_id = str(case_id_int)

        case = Case(
            claimant=claimant_addr,
            respondent=respondent_addr,
            license_type=license_type,
            source_url=source_url,
            target_url=target_url,
            claim_notes=claim_notes,
            defense_urls_json="[]",
            defense_notes="",
            claimant_bond=bond,
            respondent_bond=bigint(0),
            status=CASE_FILED,
            verdict="",
            remedy="",
            similarity_signal="",
            attribution_status="",
            license_analysis="",
            reason="",
            payout_claimant=bigint(0),
            payout_respondent=bigint(0),
        )
        self.cases[case_id] = case
        return case_id

    # ------------------------------------------------------------------------
    # 2. respond_case  -- respondent posts defense evidence, matches the bond.
    # ------------------------------------------------------------------------

    @gl.public.write.payable
    def respond_case(
        self,
        case_id: str,
        defense_urls_json: str,
        defense_notes: str,
    ) -> None:
        case = self._get_case(case_id)
        sender = gl.message.sender_address

        self._require(case.status == CASE_FILED, "Case is not open for a response")
        self._require(sender == case.respondent, "Only the named respondent may respond")

        bond = bigint(gl.message.value)
        # Escrow symmetry: the respondent must stake exactly what the claimant
        # staked. Equal bonds keep the game fair - neither side can price the
        # other out of contesting, and the pool that changes hands on a
        # decisive verdict is symmetric. (Equality also implies > 0, because a
        # case cannot exist without a positive claimant bond.)
        self._require(
            int(bond) == int(case.claimant_bond),
            "Respondent bond must equal the claimant bond",
        )

        # Defense URLs must parse as a JSON array of {"url","note"} objects.
        try:
            raw = json.loads(defense_urls_json) if defense_urls_json else []
        except Exception:
            raise Exception("Defense URLs must be valid JSON")
        self._require(isinstance(raw, list), "Defense URLs must be a JSON array")

        cleaned = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            note = str(item.get("note", "")).strip()
            if url:
                cleaned.append({"url": url, "note": note})
        self._require(
            len(cleaned) > 0,
            "At least one defense URL must be provided",
        )

        case.defense_urls_json = json.dumps(cleaned)
        case.defense_notes = defense_notes
        case.respondent_bond = bond
        case.status = CASE_CONTESTED

    # ------------------------------------------------------------------------
    # 2b. cancel_case  -- claimant withdraws an UNANSWERED filing, bond refund.
    # ------------------------------------------------------------------------
    #
    # Without this, a case whose respondent simply never posts a bond would
    # trap the claimant's stake forever: it can never reach CONTESTED, so it
    # can never be adjudicated or enforced. This is the cancellation path for
    # unanswered filings. It is only reachable while the case is still
    # CASE_FILED (no respondent bond has entered escrow yet), so it refunds
    # exactly the claimant bond and touches no one else's funds.

    @gl.public.write
    def cancel_case(self, case_id: str) -> None:
        case = self._get_case(case_id)
        self._require(
            case.status == CASE_FILED,
            "Only an unanswered case (still CASE_FILED) can be cancelled",
        )
        self._require(
            gl.message.sender_address == case.claimant,
            "Only the claimant may cancel an unanswered case",
        )

        refund = case.claimant_bond
        # No respondent bond exists in this state, so the pool is exactly the
        # claimant bond and it all returns to the claimant.
        self._require(
            int(case.respondent_bond) == 0,
            "A contested case cannot be cancelled",
        )
        case.payout_claimant = refund
        case.payout_respondent = bigint(0)
        case.status = CASE_CANCELLED

        self._pay(case.claimant, refund)

    # ------------------------------------------------------------------------
    # 3. adjudicate  -- convene AI Jury; consensus over verdict + remedy.
    # ------------------------------------------------------------------------

    @gl.public.write
    def adjudicate(self, case_id: str) -> None:
        case = self._get_case(case_id)
        self._require(
            case.status == CASE_CONTESTED,
            "Case must be CONTESTED before adjudication",
        )

        # Capture storage into locals BEFORE the nondet block. Nondet code
        # cannot touch storage. Everything below reads through closure only.
        license_type = case.license_type
        source_url = case.source_url
        target_url = case.target_url
        claim_notes = case.claim_notes
        defense_notes = case.defense_notes
        try:
            defense_items = json.loads(case.defense_urls_json)
        except Exception:
            defense_items = []
        claimant_bond_i = int(case.claimant_bond)
        respondent_bond_i = int(case.respondent_bond)

        def _fetch(url: str) -> str:
            try:
                page = gl.nondet.web.render(url, mode="text")
                return page[:6000] if page else "[EMPTY BODY]"
            except Exception:
                return "[UNREACHABLE: could not load this URL]"

        def _defense_block(items) -> str:
            if not items:
                return "[no defense URLs]"
            blocks = []
            for it in items[:5]:  # cap to keep the prompt bounded
                url = str(it.get("url", ""))
                note = str(it.get("note", ""))
                blocks.append(
                    "URL: " + url + "\nDefense note: " + note
                    + "\nContent:\n" + _fetch(url)
                )
            return "\n---\n".join(blocks)

        def _license_reference(lic: str) -> str:
            # Steer the LLM to the correct canonical text. We do NOT fetch the
            # license text via web.render because the LLM already knows the
            # canonical SPDX-listed licenses verbatim and we want to keep the
            # nondet call count bounded (validators re-run everything).
            return (
                "License in force: " + lic + ". Treat the SPDX canonical text "
                "of " + lic + " as governing. Cite the specific clause you rely on."
            )

        def leader_fn() -> typing.Any:
            source_code = _fetch(source_url)
            target_code = _fetch(target_url)
            defense_block = _defense_block(defense_items)

            prompt = (
                "You are the senior judge of an open-source license enforcement "
                "tribunal. Your ruling is binding and will move funds on chain.\n\n"
                + _license_reference(license_type) + "\n\n"
                "CLAIMANT'S SOURCE CODE (the alleged upstream work):\n"
                "URL: " + source_url + "\n"
                "Excerpt:\n" + source_code + "\n\n"
                "TARGET PRODUCT'S SOURCE (allegedly infringing):\n"
                "URL: " + target_url + "\n"
                "Excerpt:\n" + target_code + "\n\n"
                "CLAIMANT'S THEORY OF THE CASE:\n" + (claim_notes or "[not provided]") + "\n\n"
                "RESPONDENT'S DEFENSE EVIDENCE (their own repo, prior-art URLs, "
                "or a written license grant):\n" + defense_block + "\n"
                "RESPONDENT'S DEFENSE NOTES:\n" + (defense_notes or "[not provided]") + "\n\n"
                "RULING FRAMEWORK - decide in this order:\n"
                "  1. Does the target actually contain a derivative work of the "
                "     claimant's code? (substantial similarity in structure, "
                "     naming, non-trivial logic; not just idiomatic patterns.)\n"
                "  2. If yes, does the license the claimant relies on apply, and "
                "     what does its governing clause require? (GPL/AGPL: source "
                "     disclosure; MIT/BSD/Apache: attribution notice preserved; "
                "     LGPL: dynamic-link/relink allowances.)\n"
                "  3. Is the requirement satisfied on the target side (attribution "
                "     file present, source publicly mirrored, license text shipped)?\n"
                "  4. Is the claim itself abusive (target predates claimant, or "
                "     the code is trivially generic, or claimant has already been "
                "     shown to have granted a separate license)?\n\n"
                "VERDICT CATEGORIES (pick exactly one):\n"
                "  INFRINGEMENT_CONFIRMED  - derivative work is present AND a "
                "    license obligation is unmet.\n"
                "  DERIVATIVE_UNCLEAR      - similarity is partial or the license "
                "    posture is genuinely ambiguous on the evidence; case dropped.\n"
                "  NO_INFRINGEMENT         - no derivative work, OR the target's "
                "    compliance already satisfies the license.\n"
                "  RETALIATORY_CLAIM       - the filing is clearly abusive: the "
                "    target predates the claim, the code is not copyrightable, "
                "    or the claimant lacks standing.\n\n"
                "REMEDY (pick exactly one, must be consistent with the verdict):\n"
                "  RELEASE_SOURCE  - respondent must publish full corresponding source.\n"
                "  ADD_ATTRIBUTION - respondent must ship the license text and notice.\n"
                "  REMOVE_CODE     - respondent must strip the infringing code.\n"
                "  PAY_DAMAGES     - a monetary remedy is warranted (rare).\n"
                "  NONE            - no action required (use for NO_INFRINGEMENT, "
                "    DERIVATIVE_UNCLEAR, or RETALIATORY_CLAIM).\n\n"
                "Respond with ONLY a JSON object, no markdown fence, no prose "
                "outside the JSON:\n"
                "{\n"
                "  \"verdict\": \"INFRINGEMENT_CONFIRMED|DERIVATIVE_UNCLEAR|"
                "NO_INFRINGEMENT|RETALIATORY_CLAIM\",\n"
                "  \"license_analysis\": \"<how the license text applies; cite a "
                "specific clause of " + license_type + ">\",\n"
                "  \"similarity_signal\": \"STRONG|PARTIAL|WEAK|NONE\",\n"
                "  \"attribution_status\": \"PRESENT|MISSING|NOT_REQUIRED\",\n"
                "  \"remedy\": \"RELEASE_SOURCE|ADD_ATTRIBUTION|REMOVE_CODE|"
                "PAY_DAMAGES|NONE\",\n"
                "  \"reason\": \"<2-4 sentence justification grounded in the "
                "code you actually read>\"\n"
                "}"
            )
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def _parse(res) -> dict:
            if isinstance(res, (bytes, str)):
                return json.loads(res)
            return res

        def _verdicts_agree(a: str, b: str) -> bool:
            # Verdicts must match EXACTLY. Every verdict except DERIVATIVE_
            # UNCLEAR drives a decisive payout (one side takes the whole pool),
            # so we do not grant any cross-verdict tolerance: a validator that
            # reads the evidence as DERIVATIVE_UNCLEAR must NOT ratify a leader
            # who confirmed infringement or cleared the respondent, and vice
            # versa. Unclear outcomes never approve a decisive transfer - they
            # can only agree with another unclear reading. This is the core of
            # the adjudication-safety guarantee.
            return a == b

        def _remedy_consistent_with(verdict: str, remedy: str) -> bool:
            if verdict == VERDICT_INFRINGEMENT:
                return remedy in {
                    REMEDY_RELEASE_SOURCE,
                    REMEDY_ADD_ATTRIBUTION,
                    REMEDY_REMOVE_CODE,
                    REMEDY_PAY_DAMAGES,
                }
            # UNCLEAR / NO_INFRINGEMENT / RETALIATORY: no remedy action.
            return remedy == REMEDY_NONE

        def validator_fn(leader_res: typing.Any) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            try:
                leader = _parse(leader_res.calldata)
            except Exception:
                return False
            if not isinstance(leader, dict):
                return False

            l_verdict = str(leader.get("verdict", ""))
            l_remedy = str(leader.get("remedy", ""))
            l_analysis = str(leader.get("license_analysis", ""))

            if l_verdict not in VALID_VERDICTS:
                return False
            if l_remedy not in VALID_REMEDIES:
                return False
            if not _remedy_consistent_with(l_verdict, l_remedy):
                return False
            # The leader's analysis must at least name the license family;
            # a validator that sees generic legalese with no reference to
            # the license in force rejects the ruling.
            if license_type not in l_analysis and license_type.split("-")[0] not in l_analysis:
                return False

            # Independent re-adjudication. We FAIL CLOSED on every anomaly:
            # a validator exception, an unparseable re-run, or a re-run that
            # yields an invalid verdict must NOT ratify a ruling that moves
            # funds. Returning False (disagree) here costs liveness on a
            # transient web/LLM hiccup - the transaction reverts and can be
            # retried - but it guarantees that no decisive payout is ever
            # approved on the back of a validator that could not actually
            # reproduce the ruling. Safety over liveness is the correct posture
            # for an escrow that pays out on this vote.
            try:
                mine = _parse(leader_fn())
            except Exception:
                return False

            if not isinstance(mine, dict):
                return False
            m_verdict = str(mine.get("verdict", ""))
            m_remedy = str(mine.get("remedy", ""))

            if m_verdict not in VALID_VERDICTS:
                return False

            if not _verdicts_agree(l_verdict, m_verdict):
                return False

            # Remedy must also converge, but only when both sides ruled
            # INFRINGEMENT. In every non-infringement verdict remedy is NONE
            # by construction (checked above), so a match is automatic.
            if l_verdict == VERDICT_INFRINGEMENT and m_verdict == VERDICT_INFRINGEMENT:
                if l_remedy != m_remedy:
                    return False

            return True

        # We prefer gl.vm.run_nondet so validator exceptions are sandboxed and
        # distinguishable from real disagreement. This particular ruling is
        # legal-style and would also fit gl.eq_principle.prompt_comparative,
        # but the hand-written validator lets us enforce the remedy-consistency
        # and license-analysis invariants that a free-text comparator cannot.
        result = gl.vm.run_nondet(leader_fn, validator_fn)

        # Consensus succeeded, but still refuse to settle on a shape we cannot
        # read: a malformed ruling must never reach the state machine.
        try:
            verdict = _parse(result) if isinstance(result, (bytes, str)) else result
        except Exception:
            raise Exception("AI Jury returned an unparseable ruling")
        self._require(isinstance(verdict, dict), "AI Jury returned a malformed ruling")

        v = str(verdict.get("verdict", ""))
        r = str(verdict.get("remedy", ""))
        self._require(v in VALID_VERDICTS, "AI Jury returned an unknown verdict")
        self._require(r in VALID_REMEDIES, "AI Jury returned an unknown remedy")
        self._require(
            _remedy_consistent_with(v, r),
            "Verdict and remedy are inconsistent",
        )

        case.verdict = v
        case.remedy = r
        case.similarity_signal = str(verdict.get("similarity_signal", ""))
        case.attribution_status = str(verdict.get("attribution_status", ""))
        case.license_analysis = str(verdict.get("license_analysis", ""))
        case.reason = str(verdict.get("reason", ""))
        case.status = CASE_ADJUDICATED

    # ------------------------------------------------------------------------
    # 4. enforce  -- distribute bonds per verdict, close the case.
    # ------------------------------------------------------------------------
    #
    # Bond conservation is a hard invariant: payout_claimant + payout_respondent
    # ALWAYS equals claimant_bond + respondent_bond. No funds are minted, none
    # are burned, none are trapped.

    @gl.public.write
    def enforce(self, case_id: str) -> None:
        case = self._get_case(case_id)
        self._require(
            case.status == CASE_ADJUDICATED,
            "Case must be ADJUDICATED before enforcement",
        )

        c_bond = case.claimant_bond
        r_bond = case.respondent_bond
        total = c_bond + r_bond

        if case.verdict == VERDICT_INFRINGEMENT:
            # Claimant recovers own bond and takes the respondent bond as remedy.
            pay_claimant = c_bond + r_bond
            pay_respondent = bigint(0)
        elif case.verdict == VERDICT_NO_INFRINGEMENT:
            # Respondent recovers own bond and takes the claimant bond as
            # defense cost.
            pay_claimant = bigint(0)
            pay_respondent = r_bond + c_bond
        elif case.verdict == VERDICT_UNCLEAR:
            # Case dropped; each side gets its own bond back. This is
            # deliberately expensive on time and legal fees, nudging parties
            # to bring only strong cases.
            pay_claimant = c_bond
            pay_respondent = r_bond
        elif case.verdict == VERDICT_RETALIATORY:
            # Abusive filing: claimant forfeits their bond entirely to the
            # respondent, respondent recovers own bond.
            pay_claimant = bigint(0)
            pay_respondent = r_bond + c_bond
        else:
            raise Exception("Unknown verdict at enforcement time")

        # Sanity: total conservation.
        self._require(
            pay_claimant + pay_respondent == total,
            "Bond distribution does not conserve the total pool",
        )

        case.payout_claimant = pay_claimant
        case.payout_respondent = pay_respondent
        case.status = CASE_ENFORCED

        # Transfer.
        self._pay(case.claimant, pay_claimant)
        self._pay(case.respondent, pay_respondent)

    # ------------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------------

    @gl.public.view
    def get_case(self, case_id: str) -> str:
        case = self._get_case(case_id)
        try:
            defense = json.loads(case.defense_urls_json)
        except Exception:
            defense = []
        return json.dumps({
            "id": case_id,
            "claimant": _addr_hex(case.claimant),
            "respondent": _addr_hex(case.respondent),
            "license_type": case.license_type,
            "source_url": case.source_url,
            "target_url": case.target_url,
            "claim_notes": case.claim_notes,
            "defense_urls": defense,
            "defense_notes": case.defense_notes,
            "claimant_bond": int(case.claimant_bond),
            "respondent_bond": int(case.respondent_bond),
            "status": case.status,
            "verdict": case.verdict,
            "remedy": case.remedy,
            "similarity_signal": case.similarity_signal,
            "attribution_status": case.attribution_status,
            "license_analysis": case.license_analysis,
            "reason": case.reason,
            "payout_claimant": int(case.payout_claimant),
            "payout_respondent": int(case.payout_respondent),
        })

    @gl.public.view
    def get_total_cases(self) -> int:
        return int(self.next_id)

    @gl.public.view
    def get_supported_licenses(self) -> str:
        return json.dumps(sorted(LICENSE_FAMILIES))
