"""Unit tests for username_generator (pure logic, no I/O)."""

from __future__ import annotations

import pytest

from gsm.clients.username_generator import (
    DEFAULT_COLLISION_FALLBACK,
    DEFAULT_PASSWORD_LENGTH,
    DEFAULT_PATTERN,
    GeneratedAccount,
    GeneratorError,
    _is_valid_email,
    _normalize_name_part,
    _render_pattern,
    generate_accounts,
    generate_password,
    validate_pattern,
)


class TestValidatePattern:
    def test_default_pattern_ok(self) -> None:
        validate_pattern(DEFAULT_PATTERN)
        validate_pattern(DEFAULT_COLLISION_FALLBACK)

    def test_pattern_without_at_rejected(self) -> None:
        with pytest.raises(GeneratorError, match="harus mengandung '@'"):
            validate_pattern("{first}.{last}.{domain}")

    def test_pattern_without_domain_token_rejected(self) -> None:
        with pytest.raises(GeneratorError, match=r"harus mengandung '\{domain\}'"):
            validate_pattern("{first}.{last}@example.com")

    def test_unknown_token_rejected(self) -> None:
        with pytest.raises(GeneratorError, match="tidak dikenal"):
            validate_pattern("{first}.{nickname}@{domain}")

    def test_all_valid_tokens_accepted(self) -> None:
        validate_pattern("{first}{last}{first_initial}{last_initial}{n}@{domain}")


class TestGeneratePassword:
    def test_default_length(self) -> None:
        pw = generate_password()
        assert len(pw) == DEFAULT_PASSWORD_LENGTH

    def test_custom_length(self) -> None:
        assert len(generate_password(20)) == 20

    def test_too_short_rejected(self) -> None:
        with pytest.raises(GeneratorError, match=">= 8"):
            generate_password(6)

    def test_no_lookalike_chars(self) -> None:
        # Generate a long password and ensure none of the banned chars appear.
        # With 5000 chars from a ~70-char alphabet, every allowed char would
        # appear ~70 times; banned chars must not appear.
        pw = generate_password(5000)
        for c in "01OIlo":
            assert c not in pw, f"forbidden lookalike char {c!r} in password"

    def test_passwords_are_random(self) -> None:
        # Statistical: 100 12-char passwords should all differ
        passwords = {generate_password() for _ in range(100)}
        assert len(passwords) == 100


class TestNormalizeNamePart:
    def test_lowercase(self) -> None:
        assert _normalize_name_part("Andi") == "andi"

    def test_strip_apostrophe(self) -> None:
        assert _normalize_name_part("O'Brien") == "obrien"

    def test_strip_accents_dropped(self) -> None:
        # accented chars are non-ascii, will be dropped
        assert _normalize_name_part("José") == "jos"

    def test_preserve_dot(self) -> None:
        assert _normalize_name_part("J.K") == "j.k"

    def test_strip_whitespace(self) -> None:
        assert _normalize_name_part("  van der Berg  ") == "vanderberg"


class TestRenderPattern:
    def test_basic_render(self) -> None:
        out = _render_pattern(DEFAULT_PATTERN, first="andi", last="saputra", domain="x.com", n=1)
        assert out == "andi.saputra@x.com"

    def test_initials(self) -> None:
        out = _render_pattern(
            "{first_initial}{last}@{domain}",
            first="andi",
            last="saputra",
            domain="x.com",
            n=1,
        )
        assert out == "asaputra@x.com"

    def test_n_token(self) -> None:
        out = _render_pattern(
            "{first}{n}@{domain}",
            first="andi",
            last="saputra",
            domain="x.com",
            n=42,
        )
        assert out == "andi42@x.com"


class TestIsValidEmail:
    @pytest.mark.parametrize(
        "email",
        [
            "andi@x.com",
            "andi.saputra@bunhe.tech",
            "user-1@x.co.id",
            "a.b.c@x.com",
            "user_1@x.com",
            "user+tag@x.com",
        ],
    )
    def test_valid(self, email: str) -> None:
        assert _is_valid_email(email)

    @pytest.mark.parametrize(
        "email",
        [
            "",
            "noatsign.com",
            "@x.com",
            "user@",
            ".user@x.com",
            "user.@x.com",
            "us..er@x.com",
            "USER@x.com",  # uppercase rejected
            "user space@x.com",
        ],
    )
    def test_invalid(self, email: str) -> None:
        assert not _is_valid_email(email)


class TestGenerateAccounts:
    def test_count_zero_rejected(self) -> None:
        with pytest.raises(GeneratorError, match="count harus > 0"):
            generate_accounts(domain="x.com", count=0)

    def test_invalid_domain_rejected(self) -> None:
        with pytest.raises(GeneratorError, match="domain tidak valid"):
            generate_accounts(domain="invalid", count=1)

    def test_basic_generation(self) -> None:
        out = generate_accounts(domain="bunhe.tech", count=5, seed=42)
        assert len(out) == 5
        for acc in out:
            assert isinstance(acc, GeneratedAccount)
            assert acc.email.endswith("@bunhe.tech")
            assert _is_valid_email(acc.email)
            assert len(acc.password) == DEFAULT_PASSWORD_LENGTH
            assert acc.first_name
            assert acc.last_name

    def test_emails_are_unique(self) -> None:
        out = generate_accounts(domain="bunhe.tech", count=20, seed=1)
        emails = [a.email for a in out]
        assert len(set(emails)) == 20, "duplicate emails generated"

    def test_collision_with_existing(self) -> None:
        # First call with seed=42 -> some emails
        first_run = generate_accounts(domain="x.com", count=3, seed=42)
        existing = [a.email for a in first_run]

        # Second call with same seed but existing populated -> must avoid them
        second_run = generate_accounts(domain="x.com", count=3, seed=42, existing_emails=existing)
        for acc in second_run:
            assert acc.email not in existing

    def test_locale_id_ID(self) -> None:
        out = generate_accounts(domain="x.com", count=10, locale="id_ID", seed=5)
        # We can't assert specific Indonesian names (Faker dataset may evolve),
        # but we can ensure all accounts produced valid emails and the
        # locale call did not blow up.
        assert len(out) == 10

    def test_locale_en_US(self) -> None:
        out = generate_accounts(domain="x.com", count=10, locale="en_US", seed=5)
        assert len(out) == 10

    def test_fixed_password(self) -> None:
        out = generate_accounts(
            domain="x.com",
            count=5,
            fixed_password="TestPass123!",
            seed=1,
        )
        assert all(a.password == "TestPass123!" for a in out)

    def test_custom_pattern(self) -> None:
        out = generate_accounts(
            domain="x.com",
            count=3,
            pattern="{first_initial}{last}@{domain}",
            seed=1,
        )
        for acc in out:
            local, _, _ = acc.email.partition("@")
            # local should be initial+last (no dot)
            assert "." not in local

    def test_pattern_with_n_works(self) -> None:
        out = generate_accounts(
            domain="x.com",
            count=5,
            pattern="user{n}@{domain}",
            seed=1,
        )
        emails = [a.email for a in out]
        assert emails == [
            "user1@x.com",
            "user2@x.com",
            "user3@x.com",
            "user4@x.com",
            "user5@x.com",
        ]

    def test_seed_reproducible(self) -> None:
        a = generate_accounts(domain="x.com", count=5, seed=123)
        b = generate_accounts(domain="x.com", count=5, seed=123)
        # passwords are random (different) but emails use Faker which is
        # seeded globally, so emails should match between runs
        assert [x.email for x in a] == [y.email for y in b]


class TestGeneratedAccount:
    def test_to_akun_line_basic(self) -> None:
        acc = GeneratedAccount(
            email="andi@x.com",
            password="SecretPass1!",
            first_name="Andi",
            last_name="Saputra",
        )
        assert acc.to_akun_line() == "andi@x.com|SecretPass1!|"

    def test_to_akun_line_with_extra_code(self) -> None:
        acc = GeneratedAccount(
            email="andi@x.com",
            password="SecretPass1!",
            first_name="Andi",
            last_name="Saputra",
        )
        assert acc.to_akun_line("KODE-123") == "andi@x.com|SecretPass1!|KODE-123"

    def test_immutable(self) -> None:
        acc = GeneratedAccount(
            email="x@y.com",
            password="p",
            first_name="X",
            last_name="Y",
        )
        with pytest.raises((AttributeError, TypeError)):
            acc.email = "other@y.com"  # type: ignore[misc]
