"""Shared constants for Google Workspace DNS records."""

GOOGLE_MX_HOSTS: frozenset[str] = frozenset(
    {
        "aspmx.l.google.com",
        "alt1.aspmx.l.google.com",
        "alt2.aspmx.l.google.com",
        "alt3.aspmx.l.google.com",
        "alt4.aspmx.l.google.com",
    }
)

GOOGLE_MX_RECORDS: list[dict[str, str | int]] = [
    {"content": "ASPMX.L.GOOGLE.COM", "priority": 1},
    {"content": "ALT1.ASPMX.L.GOOGLE.COM", "priority": 5},
    {"content": "ALT2.ASPMX.L.GOOGLE.COM", "priority": 5},
    {"content": "ALT3.ASPMX.L.GOOGLE.COM", "priority": 10},
    {"content": "ALT4.ASPMX.L.GOOGLE.COM", "priority": 10},
]

__all__ = ["GOOGLE_MX_HOSTS", "GOOGLE_MX_RECORDS"]
