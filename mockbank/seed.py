"""Synthetic members. Every personal value here is a fake canary that must never reach evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class Share:
    name: str
    code: str
    balance: Decimal


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str
    ssn: str
    dob: str
    email: str
    phone: str
    address: str
    card: str
    shares: tuple[Share, ...] = field(default_factory=tuple)
    restricted: bool = False


MEMBERS: dict[str, Member] = {
    m.member_id: m
    for m in (
        Member(
            "48213",
            "Jane Q. Testmember",
            "900-55-0101",
            "04/12/1981",
            "jane.testmember@example.com",
            "(555) 010-4477",
            "12 Elm Street, Springfield",
            "4111 1111 1111 1111",
            (
                Share("Savings", "S01", Decimal("8812.40")),
                Share("Checking", "S10", Decimal("1204.11")),
                Share("Holiday Club", "S05", Decimal("250.00")),
            ),
        ),
        Member(
            "36620",
            "Ann B. Sample",
            "900-55-0202",
            "11/30/1975",
            "ann.sample@example.com",
            "(555) 010-2231",
            "4 Birch Lane, Shelbyville",
            "5555 5555 5555 4444",
            (
                Share("Savings", "S01", Decimal("125.00")),
                Share("Certificate", "C12", Decimal("15000.00")),
            ),
        ),
        Member(
            "51007",
            "Rex T. Restricted",
            "900-55-0303",
            "02/02/1960",
            "rex.restricted@example.com",
            "(555) 010-9090",
            "9 Oak Court, Capital City",
            "4000 0566 5566 5556",
            (Share("Savings", "S01", Decimal("99.99")),),
            restricted=True,
        ),
    )
}

# App-side validation: well-formed but rejected by the core system.
RESERVED_IDS = frozenset({"00000"})

SHARE_TYPES = ("Savings", "Certificate", "Holiday Club")

CANARIES: tuple[str, ...] = tuple(
    value
    for m in MEMBERS.values()
    for value in (m.name, m.ssn, m.dob, m.email, m.phone, m.address, m.card)
)
