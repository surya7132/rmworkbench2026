"""Generators and validators for Indian corporate identifiers.

All identifiers are SYNTHETIC but follow the real formats so that screens,
exports and extraction logic behave like they would on real data.

  CIN  Corporate Identification Number, 21 chars (MCA)
       L|U + 5-digit NIC + 2-letter state + 4-digit year + ownership + 6-digit reg no
  PAN  Permanent Account Number, 10 chars: AAAPL1234C
       4th char = holder type (C company, P person), 5th = first letter of name
  LEI  Legal Entity Identifier, 20 chars, ISO 17442, mod 97-10 check digits
  DIN  Director Identification Number, 8 digits
"""
import random
import re

CIN_RE = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}(PLC|PTC|GOI|FTC|NPL|SGC|ULT|OPC)\d{6}$")
PAN_RE = re.compile(r"^[A-Z]{3}[CPFHATBLJG][A-Z]\d{4}[A-Z]$")
LEI_RE = re.compile(r"^[A-Z0-9]{18}\d{2}$")
DIN_RE = re.compile(r"^\d{8}$")
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALNUM = "0123456789" + ALPHA


def make_cin(rng, listed, nic, state, year, regno=None):
    own = "PLC" if listed else "PTC"
    regno = regno if regno is not None else rng.randint(100000, 399999)
    return f"{'L' if listed else 'U'}{nic}{state}{year}{own}{regno:06d}"


def make_pan(rng, name, kind="C"):
    first = next((ch for ch in name.upper() if ch.isalpha()), "X")
    head = "".join(rng.choice(ALPHA) for _ in range(3))
    return f"{head}{kind}{first}{rng.randint(1000, 9999)}{rng.choice(ALPHA)}"


def _lei_numeric(s):
    return "".join(str(int(ch, 36)) for ch in s)


def make_lei(rng, prefix="335800"):
    """20 chars: 6-char prefix (LOU), 12 random alphanumerics, 2 check digits."""
    body = prefix + "".join(rng.choice(ALNUM) for _ in range(12))
    check = 98 - (int(_lei_numeric(body + "00")) % 97)
    return f"{body}{check:02d}"


def lei_ok(lei):
    return bool(LEI_RE.match(lei)) and int(_lei_numeric(lei)) % 97 == 1


def make_din(rng):
    return f"{rng.randint(1000000, 9999999):08d}"
