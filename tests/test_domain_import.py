"""Unit tests for workflows/domain_import.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gsm.clients.cloudflare import ZoneInfo
from gsm.models.domain import DomainRecord, DomainStatus
from gsm.workflows.domain_import import (
    ImportableZone,
    ImportClassification,
    discover_importable_zones,
    filter_actionable,
    label_for,
    zone_names_only,
)


def _zone(name: str, zone_id: str = "z-123") -> ZoneInfo:
    return ZoneInfo(
        zone_id=zone_id,
        name=name,
        nameservers=["ns1.cloudflare.com", "ns2.cloudflare.com"],
        created=False,
    )


@pytest.fixture
def cf_with_zones():
    """A mocked CloudflareClient returning a fixed list of zones."""

    def _make(zones):
        cf = MagicMock()
        cf.list_zones.return_value = zones
        return cf

    return _make


@pytest.fixture
def empty_ledger():
    ledger = MagicMock()
    ledger.get_domain.return_value = None
    return ledger


@pytest.fixture
def ledger_with_records():
    """A mocked Ledger keyed on domain name."""

    def _make(records: dict[str, DomainStatus]):
        ledger = MagicMock()

        def get_domain(name):
            status = records.get(name)
            if status is None:
                return None
            return DomainRecord(name=name, status=status)

        ledger.get_domain.side_effect = get_domain
        return ledger

    return _make


class TestDiscoverNoLedger:
    def test_all_new_when_ledger_empty(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([_zone("a.com"), _zone("b.com"), _zone("c.com")])
        zones = discover_importable_zones(cf, empty_ledger)
        assert len(zones) == 3
        assert all(z.classification is ImportClassification.NEW for z in zones)

    def test_sorted_by_name(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([_zone("c.com"), _zone("a.com"), _zone("b.com")])
        zones = discover_importable_zones(cf, empty_ledger)
        names = [z.name for z in zones]
        assert names == ["a.com", "b.com", "c.com"]

    def test_empty_cf_returns_empty(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([])
        zones = discover_importable_zones(cf, empty_ledger)
        assert zones == []


class TestDiscoverWithLedger:
    def test_verified_classified_as_already_verified(
        self, cf_with_zones, ledger_with_records
    ) -> None:
        cf = cf_with_zones([_zone("a.com"), _zone("b.com")])
        ledger = ledger_with_records({"a.com": DomainStatus.VERIFIED})
        zones = discover_importable_zones(cf, ledger)
        by_name = {z.name: z for z in zones}
        assert by_name["a.com"].classification is ImportClassification.ALREADY_VERIFIED
        assert by_name["b.com"].classification is ImportClassification.NEW

    def test_in_progress_classified_as_already_imported(
        self, cf_with_zones, ledger_with_records
    ) -> None:
        cf = cf_with_zones([_zone("a.com"), _zone("b.com")])
        ledger = ledger_with_records(
            {
                "a.com": DomainStatus.DNS_PENDING,
                "b.com": DomainStatus.GSUITE_ADDED,
            }
        )
        zones = discover_importable_zones(cf, ledger)
        for z in zones:
            assert z.classification is ImportClassification.ALREADY_IMPORTED

    def test_ledger_status_preserved_in_zone(self, cf_with_zones, ledger_with_records) -> None:
        cf = cf_with_zones([_zone("a.com")])
        ledger = ledger_with_records({"a.com": DomainStatus.DNS_PENDING})
        zones = discover_importable_zones(cf, ledger)
        assert zones[0].ledger_status is DomainStatus.DNS_PENDING


class TestFilterGlob:
    def test_glob_filter_dot_tech(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([_zone("foo.tech"), _zone("bar.com"), _zone("baz.tech")])
        zones = discover_importable_zones(cf, empty_ledger, filter_glob="*.tech")
        names = [z.name for z in zones]
        assert names == ["baz.tech", "foo.tech"]

    def test_glob_case_insensitive(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([_zone("FOO.TECH"), _zone("bar.com")])
        zones = discover_importable_zones(cf, empty_ledger, filter_glob="*.TECH")
        assert len(zones) == 1

    def test_no_match_returns_empty(self, cf_with_zones, empty_ledger) -> None:
        cf = cf_with_zones([_zone("foo.com"), _zone("bar.com")])
        zones = discover_importable_zones(cf, empty_ledger, filter_glob="*.xyz")
        assert zones == []


class TestFilterActionable:
    def test_drops_verified(self) -> None:
        zones = [
            ImportableZone(
                name="a.com",
                zone_id="z1",
                nameservers=(),
                classification=ImportClassification.NEW,
                ledger_status=None,
            ),
            ImportableZone(
                name="b.com",
                zone_id="z2",
                nameservers=(),
                classification=ImportClassification.ALREADY_VERIFIED,
                ledger_status=DomainStatus.VERIFIED,
            ),
            ImportableZone(
                name="c.com",
                zone_id="z3",
                nameservers=(),
                classification=ImportClassification.ALREADY_IMPORTED,
                ledger_status=DomainStatus.DNS_PENDING,
            ),
        ]
        filtered = filter_actionable(zones)
        names = [z.name for z in filtered]
        assert names == ["a.com", "c.com"]

    def test_empty_input(self) -> None:
        assert filter_actionable([]) == []


class TestZoneNamesOnly:
    def test_extracts_names(self) -> None:
        zones = [
            ImportableZone(
                name="a.com",
                zone_id="z1",
                nameservers=(),
                classification=ImportClassification.NEW,
                ledger_status=None,
            ),
            ImportableZone(
                name="b.com",
                zone_id="z2",
                nameservers=(),
                classification=ImportClassification.NEW,
                ledger_status=None,
            ),
        ]
        assert zone_names_only(zones) == ["a.com", "b.com"]


class TestLabelFor:
    def test_new(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.NEW,
            ledger_status=None,
        )
        assert label_for(z) == "NEW"

    def test_in_progress_with_status(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.ALREADY_IMPORTED,
            ledger_status=DomainStatus.DNS_PENDING,
        )
        label = label_for(z)
        assert "in progress" in label
        assert "dns_pending" in label

    def test_verified(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.ALREADY_VERIFIED,
            ledger_status=DomainStatus.VERIFIED,
        )
        assert label_for(z) == "verified"


class TestImportableZoneActionable:
    def test_new_is_actionable(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.NEW,
            ledger_status=None,
        )
        assert z.is_actionable

    def test_in_progress_is_actionable(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.ALREADY_IMPORTED,
            ledger_status=DomainStatus.DNS_PENDING,
        )
        assert z.is_actionable

    def test_verified_is_not_actionable(self) -> None:
        z = ImportableZone(
            name="a.com",
            zone_id="z1",
            nameservers=(),
            classification=ImportClassification.ALREADY_VERIFIED,
            ledger_status=DomainStatus.VERIFIED,
        )
        assert not z.is_actionable
