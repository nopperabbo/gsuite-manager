"""Shared helpers for users subcommands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from gsm.cli._shared import console, err_console
from gsm.models.results import ResultKind

__all__ = ["LICENSE_MAP", "_assign_licenses", "_resolve_user_targets"]

LICENSE_MAP = {
    "education": ("Google-Apps", "Google-Apps-For-Education"),
    "gmail-only": ("Google-Apps", "1010070004"),
    "education-standard": ("101031", "1010310005"),
    "education-plus": ("101031", "1010310009"),
}


def _assign_licenses(runtime: Any, results: list[Any], license_key: str) -> None:
    from gsm.clients.google_admin import GoogleAdminError

    if license_key in LICENSE_MAP:
        product_id, sku_id = LICENSE_MAP[license_key]
    else:
        parts = license_key.split("/", 1)
        if len(parts) != 2:
            err_console.print(
                f"[yellow][!][/yellow] License '{license_key}' not recognized. "
                f"Valid: {', '.join(LICENSE_MAP.keys())} atau 'productId/skuId'."
            )
            return
        product_id, sku_id = parts

    success = 0
    for r in results:
        if r.kind != ResultKind.SUCCESS:
            continue
        try:
            runtime.admin.assign_license(r.identifier, sku_id, product_id)
            success += 1
        except GoogleAdminError as e:
            err_console.print(f"[yellow][!][/yellow] License {r.identifier}: {e}")
    console.print(f"[green][+][/green] License assigned to {success} user(s).")


def _resolve_user_targets(runtime: Any, *, file: Path | None, domain: str | None) -> list[str]:
    if file:
        from gsm.cli._shared import read_lines
        return read_lines(file)
    if domain:
        from gsm.clients.google_admin import GoogleAdminError
        try:
            ws_users = runtime.admin.list_users(domain=domain)
        except GoogleAdminError as e:
            err_console.print(f"[red][-][/red] {e}")
            raise typer.Exit(code=2) from e
        return [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
    err_console.print("[red][-][/red] Harus kasih --domain atau --file.")
    raise typer.Exit(code=2)
