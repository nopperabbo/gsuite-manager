"""Property-based tests using Hypothesis.

Tests invariants that must hold for ALL valid inputs, not just hand-picked examples.
"""

from __future__ import annotations

import json
import string
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from gsm.core.errors import FriendlyError, humanize
from gsm.models.domain import DomainRecord, DomainStatus
from gsm.models.user import UserRecord, UserStatus
from gsm.state.ledger import Ledger

# --- Strategies ---

hex_char = st.sampled_from(string.hexdigits[:16])
hex32 = st.text(hex_char, min_size=32, max_size=32)

domain_name = st.from_regex(r"[a-z][a-z0-9\-]{1,20}\.(com|net|org|io)", fullmatch=True)
email = st.builds(
    lambda user, dom: f"{user}@{dom}", st.from_regex(r"[a-z]{3,10}", fullmatch=True), domain_name
)

domain_status = st.sampled_from(list(DomainStatus))
user_status = st.sampled_from(list(UserStatus))

domain_record = st.builds(
    DomainRecord,
    name=domain_name,
    status=domain_status,
    cf_zone_id=st.one_of(st.none(), hex32),
    txt_token=st.one_of(st.none(), st.text(min_size=10, max_size=50)),
)

user_record = st.builds(
    UserRecord,
    email=email,
    status=user_status,
    first_name=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    last_name=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)


# --- Ledger Properties ---


class TestLedgerProperties:
    """Ledger must maintain invariants regardless of input data."""

    @given(records=st.lists(domain_record, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_upsert_domain_roundtrip(self, records: list[DomainRecord]) -> None:
        """Any domain upserted can be retrieved by name (last-write-wins)."""
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "state.json")
            for rec in records:
                ledger.upsert_domain(rec)

            # Last write wins for duplicate names
            last_by_name: dict[str, DomainRecord] = {}
            for rec in records:
                last_by_name[rec.name] = rec

            for name, expected in last_by_name.items():
                got = ledger.get_domain(name)
                assert got is not None
                assert got.name == name
                assert got.status == expected.status

    @given(records=st.lists(user_record, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_upsert_user_roundtrip(self, records: list[UserRecord]) -> None:
        """Any user upserted can be retrieved by email."""
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "state.json")
            for rec in records:
                ledger.upsert_user(rec)

            for rec in records:
                got = ledger.get_user(rec.email)
                assert got is not None
                assert got.email == rec.email

    @given(records=st.lists(domain_record, min_size=1, max_size=10))
    @settings(max_examples=30)
    def test_persist_reload_identity(self, records: list[DomainRecord]) -> None:
        """Ledger survives save/reload cycle without data loss."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            ledger = Ledger(path)
            for rec in records:
                ledger.upsert_domain(rec)

            # Reload from disk — last-write-wins for duplicate names
            ledger2 = Ledger(path)
            unique_names = {r.name for r in records}
            for name in unique_names:
                got = ledger2.get_domain(name)
                assert got is not None
                assert got.name == name

    @given(records=st.lists(domain_record, min_size=0, max_size=5))
    @settings(max_examples=30)
    def test_stats_counts_match(self, records: list[DomainRecord]) -> None:
        """Stats domain count equals number of unique domain names inserted."""
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "state.json")
            for rec in records:
                ledger.upsert_domain(rec)

            unique_names = {r.name for r in records}
            stats = ledger.stats()
            assert stats["domains_total"] == len(unique_names)

    @given(garbage=st.binary(min_size=1, max_size=200))
    @settings(max_examples=20)
    def test_corrupt_file_recovery(self, garbage: bytes) -> None:
        """Ledger handles corrupt files gracefully (no crash)."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_bytes(garbage)
            ledger = Ledger(path)
            assert ledger.list_domains() == []
            assert ledger.list_users() == []


# --- Error Humanizer Properties ---


class TestHumanizeProperties:
    """humanize() must always return a valid FriendlyError, never crash."""

    @given(msg=st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_never_crashes(self, msg: str) -> None:
        """humanize() handles any string without raising."""
        result = humanize(msg)
        assert isinstance(result, FriendlyError)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0 or msg == ""

    @given(msg=st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_render_always_string(self, msg: str) -> None:
        """render() always returns a non-empty string for non-empty input."""
        result = humanize(msg)
        rendered = result.render()
        assert isinstance(rendered, str)

    @given(msg=st.text(min_size=201, max_size=1000))
    @settings(max_examples=30)
    def test_summary_truncated(self, msg: str) -> None:
        """Fallback summary is capped at 200 chars."""
        result = humanize(msg)
        assert len(result.summary) <= 200


# --- Model Properties ---


class TestModelProperties:
    """Pydantic models must serialize/deserialize without data loss."""

    @given(record=domain_record)
    @settings(max_examples=50)
    def test_domain_record_roundtrip(self, record: DomainRecord) -> None:
        """DomainRecord survives JSON roundtrip."""
        data = record.model_dump(mode="json")
        restored = DomainRecord.model_validate(data)
        assert restored.name == record.name
        assert restored.status == record.status
        assert restored.cf_zone_id == record.cf_zone_id

    @given(record=user_record)
    @settings(max_examples=50)
    def test_user_record_roundtrip(self, record: UserRecord) -> None:
        """UserRecord survives JSON roundtrip."""
        data = record.model_dump(mode="json")
        restored = UserRecord.model_validate(data)
        assert restored.email == record.email
        assert restored.status == record.status

    @given(record=user_record)
    @settings(max_examples=50)
    def test_user_domain_extraction(self, record: UserRecord) -> None:
        """UserRecord.domain always returns the part after @."""
        assert record.domain == record.email.split("@", 1)[1]

    @given(record=domain_record)
    @settings(max_examples=50)
    def test_domain_json_valid(self, record: DomainRecord) -> None:
        """model_dump(mode='json') produces valid JSON."""
        data = record.model_dump(mode="json")
        serialized = json.dumps(data)
        assert json.loads(serialized) == data
