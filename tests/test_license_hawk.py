"""
gltest suite for LicenseHawk.

Run with:
    gltest tests/test_license_hawk.py                    # localnet
    gltest tests/test_license_hawk.py --network studionet

Covers the deterministic core of the contract - state machine, bond math,
permissions, edge cases - plus one integration test that mocks the AI Jury
(LLM + web.render) and asserts bond conservation after enforcement.
"""

import json
import pytest
from gltest import get_contract_factory, create_account
from gltest.assertions import tx_execution_succeeded, tx_execution_failed


CLAIMANT_BOND = 1_000_000
RESPONDENT_BOND = 1_000_000


def _deploy(factory, owner):
    return factory.deploy(args=[], account=owner)


def _tx(contract, method, args=None, value=0, account=None, transaction_context=None):
    if account is not None:
        contract.account = account
    return getattr(contract, method)(args=args).transact(
        value=value, transaction_context=transaction_context
    )


def _defense_urls():
    return json.dumps([
        {"url": "https://example.org/defense/notice.txt", "note": "attribution file"},
        {"url": "https://example.org/defense/prior-art.txt", "note": "predates claim"},
    ])


def _open(contract, claimant, respondent):
    return _tx(
        contract,
        "file_case",
        args=[
            respondent.address,
            "https://example.org/source/main.py",
            "https://example.org/target/main.py",
            "MIT",
            "Target ships our MIT-licensed parser without the required notice.",
        ],
        value=CLAIMANT_BOND,
        account=claimant,
    )


# ---------------------------------------------------------------------------
# State machine + permission tests (deterministic only, no LLM needed)
# ---------------------------------------------------------------------------


def test_file_case_happy_path():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    receipt = _open(contract, claimant, respondent)
    assert tx_execution_succeeded(receipt)

    total = contract.get_total_cases(args=[]).call()
    assert total == 1

    state = json.loads(contract.get_case(args=["0"]).call())
    assert state["status"] == "CASE_FILED"
    assert state["license_type"] == "MIT"
    assert state["claimant_bond"] == CLAIMANT_BOND
    assert state["respondent_bond"] == 0


def test_file_case_zero_bond_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    receipt = _tx(
        contract,
        "file_case",
        args=[
            respondent.address,
            "https://example.org/a",
            "https://example.org/b",
            "MIT",
            "note",
        ],
        value=0,
        account=claimant,
    )
    assert tx_execution_failed(receipt)


def test_file_case_self_filing_rejected():
    owner = create_account()
    claimant = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    receipt = _tx(
        contract,
        "file_case",
        args=[
            claimant.address,
            "https://example.org/a",
            "https://example.org/b",
            "MIT",
            "note",
        ],
        value=CLAIMANT_BOND,
        account=claimant,
    )
    assert tx_execution_failed(receipt)


def test_file_case_unknown_license_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    receipt = _tx(
        contract,
        "file_case",
        args=[
            respondent.address,
            "https://example.org/a",
            "https://example.org/b",
            "WTFPL",
            "note",
        ],
        value=CLAIMANT_BOND,
        account=claimant,
    )
    assert tx_execution_failed(receipt)


def test_respond_by_wrong_party_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    stranger = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    receipt = _tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "defense notes"],
        value=RESPONDENT_BOND,
        account=stranger,
    )
    assert tx_execution_failed(receipt)


def test_respond_zero_bond_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    receipt = _tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "notes"],
        value=0,
        account=respondent,
    )
    assert tx_execution_failed(receipt)


def test_respond_missing_defense_urls_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    receipt = _tx(
        contract,
        "respond_case",
        args=["0", "[]", "notes"],
        value=RESPONDENT_BOND,
        account=respondent,
    )
    assert tx_execution_failed(receipt)


def test_respondent_bond_must_equal_claimant_bond():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    # Bond too low - must be rejected (escrow symmetry).
    low = _tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "notes"],
        value=CLAIMANT_BOND - 1,
        account=respondent,
    )
    assert tx_execution_failed(low)

    # Bond too high - also rejected.
    high = _tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "notes"],
        value=CLAIMANT_BOND + 1,
        account=respondent,
    )
    assert tx_execution_failed(high)

    # Exact match - accepted, case advances to CONTESTED.
    ok = _tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "notes"],
        value=CLAIMANT_BOND,
        account=respondent,
    )
    assert tx_execution_succeeded(ok)
    state = json.loads(contract.get_case(args=["0"]).call())
    assert state["status"] == "CASE_CONTESTED"
    assert state["respondent_bond"] == CLAIMANT_BOND


def test_cancel_unanswered_case_refunds_claimant():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)

    receipt = _tx(contract, "cancel_case", args=["0"], account=claimant)
    assert tx_execution_succeeded(receipt)

    state = json.loads(contract.get_case(args=["0"]).call())
    assert state["status"] == "CASE_CANCELLED"
    # Full claimant bond is refunded; nothing goes to the respondent.
    assert state["payout_claimant"] == CLAIMANT_BOND
    assert state["payout_respondent"] == 0


def test_cancel_by_non_claimant_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    stranger = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    receipt = _tx(contract, "cancel_case", args=["0"], account=stranger)
    assert tx_execution_failed(receipt)


def test_cancel_after_response_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    assert tx_execution_succeeded(_tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "notes"],
        value=RESPONDENT_BOND,
        account=respondent,
    ))
    # Once contested, the claimant can no longer unilaterally cancel.
    receipt = _tx(contract, "cancel_case", args=["0"], account=claimant)
    assert tx_execution_failed(receipt)


def test_adjudicate_before_response_rejected():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    _open(contract, claimant, respondent)
    receipt = _tx(contract, "adjudicate", args=["0"], account=claimant)
    assert tx_execution_failed(receipt)


def test_get_case_missing_raises():
    owner = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    receipt = _tx(contract, "adjudicate", args=["999"], account=owner)
    assert tx_execution_failed(receipt)


# ---------------------------------------------------------------------------
# Integration: adjudicate + enforce with mocked LLM/web (bond conservation).
# ---------------------------------------------------------------------------


def test_full_flow_infringement_confirmed_conserves_bonds():
    owner = create_account()
    claimant = create_account()
    respondent = create_account()
    contract = _deploy(get_contract_factory("Contract"), owner)

    assert tx_execution_succeeded(_open(contract, claimant, respondent))
    assert tx_execution_succeeded(_tx(
        contract,
        "respond_case",
        args=["0", _defense_urls(), "we shipped the notice, see url 1"],
        value=RESPONDENT_BOND,
        account=respondent,
    ))

    ruling = json.dumps({
        "verdict": "INFRINGEMENT_CONFIRMED",
        "license_analysis": (
            "MIT license section 'The above copyright notice ... shall be "
            "included in all copies' is not satisfied - target ships no NOTICE."
        ),
        "similarity_signal": "STRONG",
        "attribution_status": "MISSING",
        "remedy": "ADD_ATTRIBUTION",
        "reason": "Target file mirrors claimant parser byte-for-byte with no attribution.",
    })

    context = {
        "validators": [
            {
                "plugin_config": {
                    "mock_web_response": {
                        "nondet_web_request": {
                            "https://example.org/source/main.py": "def parse(x): return x[::-1]  # MIT",
                            "https://example.org/target/main.py": "def parse(x): return x[::-1]  # copied, no attribution",
                            "https://example.org/defense/notice.txt": "NOTICE: n/a",
                            "https://example.org/defense/prior-art.txt": "n/a",
                        }
                    },
                    "mock_response": {"response": {".*": ruling}},
                }
            }
        ]
    }

    receipt = _tx(
        contract,
        "adjudicate",
        args=["0"],
        account=claimant,
        transaction_context=context,
    )
    assert tx_execution_succeeded(receipt)

    state = json.loads(contract.get_case(args=["0"]).call())
    assert state["status"] == "CASE_ADJUDICATED"
    assert state["verdict"] == "INFRINGEMENT_CONFIRMED"
    assert state["remedy"] == "ADD_ATTRIBUTION"

    assert tx_execution_succeeded(_tx(contract, "enforce", args=["0"], account=claimant))
    final = json.loads(contract.get_case(args=["0"]).call())
    assert final["status"] == "CASE_ENFORCED"
    # Core invariant: bond conservation.
    total_before = CLAIMANT_BOND + RESPONDENT_BOND
    assert final["payout_claimant"] + final["payout_respondent"] == total_before
    # INFRINGEMENT_CONFIRMED - claimant recovers own bond and takes respondent bond.
    assert final["payout_claimant"] == total_before
    assert final["payout_respondent"] == 0
