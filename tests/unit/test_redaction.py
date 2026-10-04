"""RED-01..RED-05, RED-14: nothing regulated survives the redaction layer."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr

from handrail.redaction import labelled_values, redact, redact_text, sensitive_values
from handrail.redaction.patterns import aba_ok, luhn_ok
from handrail.schema import parse_artifact

pytestmark = pytest.mark.unit

# Canary values: syntactically valid, fake. Card passes Luhn, routing passes ABA.
SSN = "123-45-6789"
CARD = "4111 1111 1111 1111"
ROUTING = "021000021"
ACCOUNT = "000123456789"
EMAIL = "jane.doe@example.com"
PHONE = "(555) 010-4477"


@pytest.mark.parametrize(
    ("value", "label"),
    [
        (SSN, "ssn"),
        (CARD, "card"),
        ("4111-1111-1111-1111", "card"),
        (ROUTING, "routing"),
        (ACCOUNT, "account"),
        (EMAIL, "email"),
        (PHONE, "phone"),
        ("+1 555.010.4477", "phone"),
    ],
)
def test_red01_patterns(value: str, label: str) -> None:
    out = redact_text(f"member note: {value} end")
    assert value not in out
    assert f"[REDACTED:{label}]" in out


def test_red01_dob_in_context() -> None:
    out = redact_text("DOB: 04/12/1981, joined 2019")
    assert "04/12/1981" not in out
    assert "joined 2019" in out


def test_red01_glued_to_letters() -> None:
    assert SSN not in redact_text(f"ssn{SSN}x")


def test_checksums() -> None:
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
    assert aba_ok(ROUTING)
    assert not aba_ok("123456789")


def test_ordinary_text_untouched() -> None:
    text = "Step 3 of 4 took 812 ms; balance table has 2 rows (v3.4)."
    assert redact_text(text) == text


_ssn = st.from_regex(r"\A\d{3}-\d{2}-\d{4}\Z")
_email = st.from_regex(r"\A[a-z]{1,10}\.[a-z]{1,10}@[a-z]{2,10}\.(com|org)\Z")
_account = st.from_regex(r"\A\d{8,17}\Z")


@given(
    pii=st.one_of(_ssn, _email, _account),
    before=st.text(max_size=40),
    after=st.text(max_size=40),
    key=st.sampled_from(["note", "message", "observed", "event"]),
)
def test_red02_property_pii_never_survives(pii: str, before: str, after: str, key: str) -> None:
    event = {key: f"{before} {pii} {after}", "nested": [{"deep": pii}]}
    out = repr(redact(event))
    assert pii not in out


def test_red03_label_driven_output(example_dict: dict[str, Any]) -> None:
    artifact = parse_artifact(example_dict)
    values = labelled_values(artifact.outputs, {"savings_balance": "8812.40"}, prefix="output")
    with sensitive_values(values):
        out = redact({"observed": "Balance: $8812.40", "outputs": {"savings_balance": "8812.40"}})
    assert "8812.40" not in repr(out)


def test_red04_input_value_masked_everywhere(example_dict: dict[str, Any]) -> None:
    artifact = parse_artifact(example_dict)
    values = labelled_values(artifact.inputs, {"member_id": "48213"}, prefix="input")
    with sensitive_values(values):
        out = redact(
            {"url": "https://mockbank.local/member/48213?id=48213", "typed": "48213", "n": 48213}
        )
    assert "48213" not in repr(out)
    assert out["typed"] == "[REDACTED:input:member_id]"


def test_red04_registration_is_scoped() -> None:
    with sensitive_values({"input:member_id": "48213"}):
        assert "48213" not in redact_text("id 48213")
    assert "48213" in redact_text("id 48213")


def test_red04_public_values_not_registered(example_dict: dict[str, Any]) -> None:
    example_dict["inputs"]["member_id"]["sensitivity"] = "public"
    example_dict.pop("content_hash")
    example_dict["status"] = "draft"
    artifact = parse_artifact(example_dict)
    assert labelled_values(artifact.inputs, {"member_id": "48213"}, prefix="input") == {}


def test_red05_secrets_never_serialize() -> None:
    out = redact({"api": SecretStr("sk-live-abc"), "password": "hunter22", "api_key": "k-123"})
    assert "sk-live-abc" not in repr(out)
    assert "hunter22" not in repr(out)
    assert "k-123" not in repr(out)


def test_token_counts_are_not_secrets() -> None:
    assert redact({"input_tokens": 1200, "output_tokens": 88}) == {
        "input_tokens": 1200,
        "output_tokens": 88,
    }


def test_red14_exception_messages_redacted() -> None:
    out = redact(ValueError(f"lookup failed for {SSN}"))
    assert SSN not in out
    assert out.startswith("ValueError:")
