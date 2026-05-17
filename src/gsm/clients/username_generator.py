"""Username + password generator for bulk user creation.

Pure logic module - no I/O, no Workspace API calls. Designed to be imported
by the CLI `users gen` command and tested in isolation.

Pattern tokens supported (case-sensitive):
    {first}          -> first name lowercased (e.g. "andi")
    {last}           -> last name lowercased (e.g. "saputra")
    {first_initial}  -> first name initial (e.g. "a")
    {last_initial}   -> last name initial (e.g. "s")
    {n}              -> 1-based index in the batch (e.g. "1", "2")
    {domain}         -> the target domain (e.g. "bunhe.tech")

Examples:
    {first}.{last}@{domain}            -> andi.saputra@bunhe.tech
    {first_initial}{last}@{domain}     -> asaputra@bunhe.tech
    {first}{n}@{domain}                -> andi1@bunhe.tech
"""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from faker import Faker

from gsm.core.logging import get_logger

DEFAULT_PATTERN: Final[str] = "{first}.{last}@{domain}"
DEFAULT_COLLISION_FALLBACK: Final[str] = "{first}{last_initial}{n}@{domain}"
DEFAULT_PASSWORD_LENGTH: Final[int] = 12
MAX_COLLISION_ATTEMPTS: Final[int] = 50

# Alphabet for random passwords: avoid look-alike chars (0/O, 1/l/I)
# to reduce manual transcription errors when handing off to clients.
_PASSWORD_ALPHABET: Final[str] = (
    string.ascii_lowercase.translate(str.maketrans("", "", "lo"))
    + string.ascii_uppercase.translate(str.maketrans("", "", "IO"))
    + string.digits.translate(str.maketrans("", "", "01"))
    + "!@#$%^&*"
)

# Valid pattern token names, used for early validation.
_VALID_TOKENS: Final[frozenset[str]] = frozenset(
    {"first", "last", "first_initial", "last_initial", "n", "domain"}
)
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\{([a-z_]+)\}")

# Local-part validation: Google Workspace allows letters, digits,
# dots, hyphens, underscores, plus signs. Lowercase only for safety.
_LOCAL_PART_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9._+\-]+$")

_log = get_logger("clients.username_generator")


class GeneratorError(ValueError):
    """Raised when generator inputs are invalid (bad pattern, etc)."""


@dataclass(frozen=True, slots=True)
class GeneratedAccount:
    """A single generated account row, ready to be written to akun.txt."""

    email: str
    password: str
    first_name: str
    last_name: str

    def to_akun_line(self, extra_code: str = "") -> str:
        """Render in `akun.txt` format: `email|password|kode`.

        The extra_code field is optional but always emitted (empty string)
        for forward-compatibility with parse_akun_file.
        """
        return f"{self.email}|{self.password}|{extra_code}"


def validate_pattern(pattern: str) -> None:
    """Raise GeneratorError if pattern uses unknown tokens or is malformed."""
    if "@" not in pattern:
        raise GeneratorError(
            f"Pattern harus mengandung '@' (contoh: '{DEFAULT_PATTERN}'). Got: {pattern!r}"
        )
    if "{domain}" not in pattern:
        raise GeneratorError(
            f"Pattern harus mengandung '{{domain}}' (contoh: '{DEFAULT_PATTERN}'). Got: {pattern!r}"
        )
    found = set(_TOKEN_RE.findall(pattern))
    unknown = found - _VALID_TOKENS
    if unknown:
        raise GeneratorError(
            f"Token tidak dikenal: {sorted(unknown)}. Valid: {sorted(_VALID_TOKENS)}"
        )


def generate_password(length: int = DEFAULT_PASSWORD_LENGTH) -> str:
    """Generate a cryptographically secure random password.

    Uses an alphabet without look-alike characters (0/O/I/l/1) to reduce
    transcription errors when sharing with end users.

    Length must be >= 8 (sane minimum). Default 12 balances security + usability.
    """
    if length < 8:
        raise GeneratorError(f"Password length harus >= 8, got {length}.")
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _normalize_name_part(s: str) -> str:
    """Strip non-local-part chars from a name fragment.

    Faker can emit names with apostrophes, hyphens, accents. Workspace
    local-part is lowercase ascii alnum + .-_+. We:
      - lowercase
      - strip whitespace
      - drop chars not in [a-z0-9.-_+]
    """
    lowered = s.lower().strip()
    return "".join(c for c in lowered if _LOCAL_PART_RE.match(c) or c == ".")


def _render_pattern(
    pattern: str,
    *,
    first: str,
    last: str,
    domain: str,
    n: int,
) -> str:
    """Substitute pattern tokens. Caller must validate_pattern first."""
    return pattern.format(
        first=first,
        last=last,
        first_initial=first[:1] if first else "",
        last_initial=last[:1] if last else "",
        n=n,
        domain=domain,
    )


def _is_valid_email(email: str) -> bool:
    """Validate the local-part is non-empty and well-formed."""
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if not _LOCAL_PART_RE.match(local):
        return False
    # Reject leading/trailing/consecutive dots in local-part
    return not (local.startswith(".") or local.endswith(".") or ".." in local)


def generate_accounts(
    *,
    domain: str,
    count: int,
    locale: str = "id_ID",
    pattern: str = DEFAULT_PATTERN,
    collision_fallback: str = DEFAULT_COLLISION_FALLBACK,
    password_length: int = DEFAULT_PASSWORD_LENGTH,
    fixed_password: str | None = None,
    existing_emails: Iterable[str] = (),
    seed: int | None = None,
) -> list[GeneratedAccount]:
    """Generate `count` accounts for `domain`, avoiding collisions.

    Args:
        domain: Target domain (e.g. "bunhe.tech"). Lowercased internally.
        count: Number of accounts to generate. Must be > 0.
        locale: Faker locale (e.g. "id_ID", "en_US"). Pass-through to Faker.
        pattern: Email format using tokens (see module docstring).
        collision_fallback: Alternate pattern when primary collides. Must
            include {n} or another disambiguator.
        password_length: Length of generated passwords (>= 8).
        fixed_password: If set, use this for ALL accounts (testing only).
        existing_emails: Iterable of already-used emails to avoid (typically
            ledger users for this domain).
        seed: Optional Faker seed for reproducible output.

    Returns:
        List of GeneratedAccount, length == count.

    Raises:
        GeneratorError: invalid inputs, or unable to resolve collisions.
    """
    if count <= 0:
        raise GeneratorError(f"count harus > 0, got {count}.")
    if not domain or "." not in domain:
        raise GeneratorError(f"domain tidak valid: {domain!r}.")

    validate_pattern(pattern)
    validate_pattern(collision_fallback)

    domain_norm = domain.lower().strip()
    used: set[str] = {e.lower().strip() for e in existing_emails}

    fake = Faker(locale)
    if seed is not None:
        Faker.seed(seed)

    results: list[GeneratedAccount] = []
    for i in range(1, count + 1):
        first_raw = fake.first_name()
        last_raw = fake.last_name()
        first = _normalize_name_part(first_raw)
        last = _normalize_name_part(last_raw)

        # Faker can occasionally emit names that normalize to empty
        # (e.g. all non-ascii). Fall back to a deterministic placeholder.
        if not first:
            first = f"user{i}"
        if not last:
            last = "guest"

        email = _resolve_email(
            i=i,
            first=first,
            last=last,
            domain=domain_norm,
            primary_pattern=pattern,
            fallback_pattern=collision_fallback,
            used=used,
        )
        used.add(email)

        password = (
            fixed_password if fixed_password is not None else generate_password(password_length)
        )

        results.append(
            GeneratedAccount(
                email=email,
                password=password,
                first_name=first_raw.title(),
                last_name=last_raw.title(),
            )
        )

    _log.info(
        "generated_accounts",
        count=count,
        domain=domain_norm,
        locale=locale,
        existing_skipped=len(set(existing_emails) & {a.email for a in results}),
    )
    return results


def _resolve_email(
    *,
    i: int,
    first: str,
    last: str,
    domain: str,
    primary_pattern: str,
    fallback_pattern: str,
    used: set[str],
) -> str:
    """Try primary pattern first; if collision, append numeric suffix via fallback.

    The fallback pattern is rendered with n=2,3,...,MAX_COLLISION_ATTEMPTS
    until a unique email is found. If still colliding, raise.
    """
    candidate = _render_pattern(primary_pattern, first=first, last=last, domain=domain, n=i)
    if _is_valid_email(candidate) and candidate not in used:
        return candidate

    for attempt in range(2, MAX_COLLISION_ATTEMPTS + 2):
        candidate = _render_pattern(
            fallback_pattern,
            first=first,
            last=last,
            domain=domain,
            n=attempt,
        )
        if _is_valid_email(candidate) and candidate not in used:
            return candidate

    raise GeneratorError(
        f"Tidak bisa generate email unik untuk {first}.{last} di {domain} "
        f"setelah {MAX_COLLISION_ATTEMPTS} attempt. "
        f"Cek pattern fallback (harus include {{n}}) atau kurangi count."
    )
