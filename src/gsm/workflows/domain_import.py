"""Domain import workflow: discover zones from Cloudflare, filter, prepare for onboarding.

Pure logic - filtering & classification only. No I/O, no prompting; the CLI
layer handles user interaction (questionary picker) and downstream onboarding.

Typical flow:

    1. CLI calls discover_importable_zones(cf, ledger, filter_glob=...)
       -> returns list[ImportableZone] with status flags (NEW/ALREADY_IMPORTED)
    2. CLI shows interactive picker, user selects subset
    3. CLI passes selected names to onboard_domains() workflow

Separating discovery from selection from onboarding keeps each step testable
and lets the CLI swap interactive picker for --all / --filter modes without
reimplementing logic.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import StrEnum

from gsm.clients.cloudflare import CloudflareClient, ZoneInfo
from gsm.core.logging import get_logger
from gsm.models.domain import DomainStatus
from gsm.state.ledger import Ledger

_log = get_logger("workflows.domain_import")


class ImportClassification(StrEnum):
    NEW = "new"
    ALREADY_IMPORTED = "already_imported"
    ALREADY_VERIFIED = "already_verified"


@dataclass(frozen=True, slots=True)
class ImportableZone:
    """Cloudflare zone annotated with ledger status."""

    name: str
    zone_id: str
    nameservers: tuple[str, ...]
    classification: ImportClassification
    ledger_status: DomainStatus | None

    @property
    def is_actionable(self) -> bool:
        """True if this zone makes sense to import (NEW or partial onboarding)."""
        return self.classification is not ImportClassification.ALREADY_VERIFIED


def discover_importable_zones(
    cf: CloudflareClient,
    ledger: Ledger,
    *,
    filter_glob: str | None = None,
) -> list[ImportableZone]:
    """Fetch CF zones, cross-reference with ledger, optionally filter by glob.

    Returns sorted list (by name) of ImportableZone. Existing ledger entries
    are kept in the output but flagged so the CLI can render them differently
    or auto-skip them.
    """
    zones = cf.list_zones()
    if filter_glob:
        zones = [z for z in zones if fnmatch.fnmatch(z.name.lower(), filter_glob.lower())]

    importable: list[ImportableZone] = []
    for zone in zones:
        record = ledger.get_domain(zone.name)
        classification = _classify(record.status if record else None)
        importable.append(
            ImportableZone(
                name=zone.name,
                zone_id=zone.zone_id,
                nameservers=tuple(zone.nameservers),
                classification=classification,
                ledger_status=record.status if record else None,
            )
        )

    importable.sort(key=lambda z: z.name)
    _log.info(
        "discovered_zones",
        total=len(importable),
        new=sum(1 for z in importable if z.classification is ImportClassification.NEW),
        already_imported=sum(
            1 for z in importable if z.classification is ImportClassification.ALREADY_IMPORTED
        ),
        already_verified=sum(
            1 for z in importable if z.classification is ImportClassification.ALREADY_VERIFIED
        ),
        filter_glob=filter_glob,
    )
    return importable


def _classify(status: DomainStatus | None) -> ImportClassification:
    """Map ledger status to import classification.

    No ledger entry  -> NEW (never imported)
    VERIFIED         -> ALREADY_VERIFIED (no action needed)
    Anything else    -> ALREADY_IMPORTED (in progress, can resume)
    """
    if status is None:
        return ImportClassification.NEW
    if status is DomainStatus.VERIFIED:
        return ImportClassification.ALREADY_VERIFIED
    return ImportClassification.ALREADY_IMPORTED


def filter_actionable(zones: list[ImportableZone]) -> list[ImportableZone]:
    """Drop zones that are already VERIFIED - they don't need re-onboarding."""
    return [z for z in zones if z.is_actionable]


def zone_names_only(zones: list[ImportableZone]) -> list[str]:
    """Convenience: extract just the domain names for downstream onboarding."""
    return [z.name for z in zones]


_STATUS_LABEL: dict[ImportClassification, str] = {
    ImportClassification.NEW: "NEW",
    ImportClassification.ALREADY_IMPORTED: "in progress",
    ImportClassification.ALREADY_VERIFIED: "verified",
}


def label_for(zone: ImportableZone) -> str:
    """Human-readable label for picker display."""
    base = _STATUS_LABEL[zone.classification]
    if zone.classification is ImportClassification.ALREADY_IMPORTED and zone.ledger_status:
        return f"{base} ({zone.ledger_status.value})"
    return base


__all__ = [
    "ImportClassification",
    "ImportableZone",
    "ZoneInfo",
    "discover_importable_zones",
    "filter_actionable",
    "label_for",
    "zone_names_only",
]
