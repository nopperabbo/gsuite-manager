"""Tests for friendly error humanization."""

from __future__ import annotations

from gsm.core.errors import FriendlyError, humanize


class TestHumanize:
    def test_invalid_cf_token(self):
        result = humanize("Cloudflare 401: Invalid API Token")
        assert "tidak valid" in result.summary.lower()
        assert result.hint is not None
        assert "dash.cloudflare.com" in result.hint

    def test_cf_403_permission(self):
        result = humanize("Cloudflare 403 Forbidden")
        assert "permission" in result.summary.lower()
        assert "Zone:Edit" in (result.hint or "")

    def test_rate_limit(self):
        result = humanize("HTTP 429 rate limit exceeded")
        assert "rate limit" in result.summary.lower()
        assert "DELAY" in (result.hint or "")

    def test_network_timeout(self):
        result = humanize("network error: connection timeout")
        assert "koneksi" in result.summary.lower()

    def test_oauth_file_missing(self):
        result = humanize("OAuth client file not found: ./missing.json")
        assert "credentials.json" in result.summary
        assert "Google Cloud Console" in (result.hint or "")

    def test_dns_propagation_pending(self):
        result = humanize(
            "verification token could not be found on your site"
        )
        assert "TXT" in result.summary
        assert "verify --only-pending" in (result.hint or "")

    def test_already_verified_no_hint(self):
        result = humanize("Domain already verified")
        assert "sudah" in result.summary.lower()
        assert result.hint is None

    def test_duplicate_no_hint(self):
        result = humanize("409 already exists")
        assert "duplikat" in result.summary.lower() or "ada" in result.summary.lower()
        assert result.hint is None

    def test_password_policy(self):
        result = humanize("password policy violation: too weak")
        assert "policy" in result.summary.lower()
        assert "8+" in (result.hint or "")

    def test_validation_error(self):
        result = humanize("validation error for Settings: field required")
        assert "lengkap" in result.summary.lower() or "salah" in result.summary.lower()
        assert "doctor" in (result.hint or "")

    def test_unknown_error_passthrough(self):
        result = humanize("some weird unmatched error")
        assert "weird" in result.summary
        assert result.hint is None

    def test_render_with_hint(self):
        e = FriendlyError("Problem X", "Cara fix Y")
        rendered = e.render()
        assert "Problem X" in rendered
        assert "Cara fix Y" in rendered

    def test_render_without_hint(self):
        e = FriendlyError("Just a problem")
        assert e.render() == "Just a problem"

    def test_humanize_accepts_exception(self):
        result = humanize(ValueError("Invalid API Token"))
        assert "tidak valid" in result.summary.lower()
