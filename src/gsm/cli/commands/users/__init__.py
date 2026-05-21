"""`gsm users` subcommands."""

from __future__ import annotations

# Import submodules to register commands on users_app
from gsm.cli.commands.users._aliases import (
    users_alias_add,
    users_alias_list,
    users_alias_remove,
)
from gsm.cli.commands.users._app import users_app
from gsm.cli.commands.users._audit import users_audit
from gsm.cli.commands.users._crud import (
    users_add,
    users_delete,
    users_list,
    users_move,
    users_reset_password,
    users_update,
)
from gsm.cli.commands.users._gen import users_gen
from gsm.cli.commands.users._suspend import users_suspend, users_unsuspend

__all__ = [
    "users_add",
    "users_alias_add",
    "users_alias_list",
    "users_alias_remove",
    "users_app",
    "users_audit",
    "users_delete",
    "users_gen",
    "users_list",
    "users_move",
    "users_reset_password",
    "users_suspend",
    "users_unsuspend",
    "users_update",
]
