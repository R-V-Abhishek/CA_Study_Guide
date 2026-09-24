"""Crockford base32 ID generation for taxonomy nodes."""

import secrets

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_node_id(paper_code: str) -> str:
    """Generate opaque 6-char Crockford base32 node ID, e.g. P1-7KQ2MX."""
    chars = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(6))
    return f"{paper_code}-{chars}"


def is_valid_node_id(node_id: str) -> bool:
    """Validate format: P[1-6]-[0-9A-HJKMNP-TV-Z]{6}."""
    if len(node_id) != 9:
        return False
    parts = node_id.split("-")
    if len(parts) != 2:
        return False
    paper, code = parts
    if not (len(paper) == 2 and paper[0] == "P" and paper[1] in "123456"):
        return False
    if len(code) != 6:
        return False
    return all(c in CROCKFORD_ALPHABET for c in code)
