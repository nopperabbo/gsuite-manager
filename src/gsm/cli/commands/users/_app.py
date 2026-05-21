"""Typer app instance for `gsm users` — isolated to avoid circular imports."""

from __future__ import annotations

import typer

users_app = typer.Typer(
    name="users",
    help="Manage Workspace users: bulk create, inspect.",
    no_args_is_help=True,
)
