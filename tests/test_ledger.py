from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from gsm.models.domain import DomainRecord, DomainStatus
from gsm.models.user import UserRecord, UserStatus
from gsm.state.ledger import Ledger


class TestFreshLedger:
    def test_get_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "nope.json")
        assert ledger.get_domain("foo.com") is None
        assert ledger.list_domains() == []
        assert ledger.list_users() == []

    def test_creates_file_on_first_upsert(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        ledger = Ledger(path)
        ledger.upsert_domain(DomainRecord(name="bunhe.tech", status=DomainStatus.GSUITE_ADDED))
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert "bunhe.tech" in data["domains"]


class TestRoundTrip:
    def test_upsert_and_get(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        record = DomainRecord(
            name="bunhe.tech",
            status=DomainStatus.VERIFIED,
            cf_zone_id="zone-abc",
            cf_nameservers=["ns1.cf.com", "ns2.cf.com"],
            txt_token="google-site-verification=xyz",
        )
        ledger.upsert_domain(record)

        fresh = Ledger(tmp_path / "s.json")
        loaded = fresh.get_domain("bunhe.tech")
        assert loaded is not None
        assert loaded.status == DomainStatus.VERIFIED
        assert loaded.cf_zone_id == "zone-abc"
        assert loaded.cf_nameservers == ["ns1.cf.com", "ns2.cf.com"]
        assert loaded.txt_token == "google-site-verification=xyz"

    def test_upsert_user(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        record = UserRecord(
            email="alice@bunhe.tech", status=UserStatus.CREATED, first_name="Alice"
        )
        ledger.upsert_user(record)

        fresh = Ledger(tmp_path / "s.json")
        loaded = fresh.get_user("alice@bunhe.tech")
        assert loaded is not None
        assert loaded.first_name == "Alice"

    def test_first_seen_preserved_on_update(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        ledger.upsert_domain(DomainRecord(name="x.com", status=DomainStatus.PENDING))
        original = ledger.get_domain("x.com")
        assert original is not None
        first_seen_orig = original.first_seen

        updated = DomainRecord(
            name="x.com",
            status=DomainStatus.VERIFIED,
            first_seen=datetime(2000, 1, 1),
        )
        ledger.upsert_domain(updated)

        after = ledger.get_domain("x.com")
        assert after is not None
        assert after.first_seen == first_seen_orig
        assert after.status == DomainStatus.VERIFIED


class TestFiltering:
    def test_list_domains_by_status(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        ledger.upsert_domain(DomainRecord(name="a.com", status=DomainStatus.VERIFIED))
        ledger.upsert_domain(DomainRecord(name="b.com", status=DomainStatus.DNS_PENDING))
        ledger.upsert_domain(DomainRecord(name="c.com", status=DomainStatus.VERIFIED))

        verified = ledger.list_domains(status=DomainStatus.VERIFIED)
        pending = ledger.list_domains(status=DomainStatus.DNS_PENDING)
        all_domains = ledger.list_domains()

        assert {d.name for d in verified} == {"a.com", "c.com"}
        assert {d.name for d in pending} == {"b.com"}
        assert len(all_domains) == 3

    def test_list_users_by_domain(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        ledger.upsert_user(UserRecord(email="a@bunhe.tech", status=UserStatus.CREATED))
        ledger.upsert_user(UserRecord(email="b@minbu.tech", status=UserStatus.CREATED))
        ledger.upsert_user(UserRecord(email="c@bunhe.tech", status=UserStatus.PENDING))

        bunhe = ledger.list_users(domain="bunhe.tech")
        assert {u.email for u in bunhe} == {"a@bunhe.tech", "c@bunhe.tech"}


class TestCorruption:
    def test_corrupt_json_treated_as_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        path.write_text("{not valid json}")
        ledger = Ledger(path)
        assert ledger.list_domains() == []
        ledger.upsert_domain(DomainRecord(name="ok.com", status=DomainStatus.VERIFIED))
        assert ledger.get_domain("ok.com") is not None

    def test_unexpected_root_type_treated_as_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        path.write_text("[]")
        ledger = Ledger(path)
        assert ledger.list_domains() == []


class TestAtomicWrite:
    def test_no_tmp_file_after_successful_write(self, tmp_path: Path) -> None:
        path = tmp_path / "s.json"
        ledger = Ledger(path)
        ledger.upsert_domain(DomainRecord(name="x.com", status=DomainStatus.VERIFIED))
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()


class TestThreadSafety:
    def test_concurrent_upsert(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")

        def worker(i: int) -> None:
            ledger.upsert_domain(
                DomainRecord(name=f"domain{i}.com", status=DomainStatus.VERIFIED)
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ledger.list_domains()) == 20

        fresh = Ledger(tmp_path / "s.json")
        assert len(fresh.list_domains()) == 20


class TestArchive:
    def test_archive_moves_old_records(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")

        old_record = DomainRecord(
            name="old.com",
            status=DomainStatus.VERIFIED,
            first_seen=datetime.now() - timedelta(days=120),
            last_updated=datetime.now() - timedelta(days=100),
        )
        ledger._domains[old_record.name] = old_record  # type: ignore[attr-defined]
        ledger.upsert_domain(DomainRecord(name="recent.com", status=DomainStatus.VERIFIED))

        archive_path = tmp_path / "archive.json"
        moved = ledger.archive(
            before=datetime.now() - timedelta(days=90), archive_path=archive_path
        )

        assert moved == 1
        assert ledger.get_domain("old.com") is None
        assert ledger.get_domain("recent.com") is not None

        archive_data = json.loads(archive_path.read_text())
        assert "old.com" in archive_data["domains"]

    def test_archive_returns_zero_when_nothing_old(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        ledger.upsert_domain(DomainRecord(name="recent.com", status=DomainStatus.VERIFIED))
        moved = ledger.archive(
            before=datetime.now() - timedelta(days=365),
            archive_path=tmp_path / "archive.json",
        )
        assert moved == 0


class TestStats:
    def test_stats_breakdown(self, tmp_path: Path) -> None:
        ledger = Ledger(tmp_path / "s.json")
        ledger.upsert_domain(DomainRecord(name="a.com", status=DomainStatus.VERIFIED))
        ledger.upsert_domain(DomainRecord(name="b.com", status=DomainStatus.VERIFIED))
        ledger.upsert_domain(DomainRecord(name="c.com", status=DomainStatus.DNS_PENDING))
        ledger.upsert_user(UserRecord(email="x@a.com", status=UserStatus.CREATED))

        stats = ledger.stats()
        assert stats["domains_total"] == 3
        assert stats["users_total"] == 1
        assert stats["domains_verified"] == 2
        assert stats["domains_dns_pending"] == 1
