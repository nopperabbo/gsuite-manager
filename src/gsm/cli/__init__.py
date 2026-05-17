import typer

from gsm import __version__
from gsm.cli.commands.audit import audit_command
from gsm.cli.commands.dns import dns_apply_command
from gsm.cli.commands.doctor import doctor_command
from gsm.cli.commands.domains import domains_app
from gsm.cli.commands.expiry import check_expiry_command
from gsm.cli.commands.go import go_command
from gsm.cli.commands.groups import groups_app
from gsm.cli.commands.health import health_command
from gsm.cli.commands.init import init_command, setup_command
from gsm.cli.commands.ledger import ledger_app
from gsm.cli.commands.menu import menu_command
from gsm.cli.commands.users import users_app

app = typer.Typer(
    name="gsm",
    help="GSuite Manager - automate GSuite Workspace + Cloudflare domain & user operations.",
    no_args_is_help=False,
    invoke_without_command=True,
    pretty_exceptions_show_locals=False,
)

app.add_typer(domains_app)
app.add_typer(users_app)
app.add_typer(groups_app)
app.add_typer(ledger_app)
app.command("go", help="⚡ All-in-one: onboard domains + create users. Auto-detect files.")(
    go_command
)
app.command("menu", help="Interactive menu - pilih fitur manual.")(menu_command)
app.command("setup", help="Wizard interaktif - setup awal step-by-step.")(
    setup_command
)
app.command("init", help="Tulis .env template kosong (non-interaktif).")(
    init_command
)
app.command("doctor", help="Run health checks against config + connectivity.")(
    doctor_command
)
app.command(
    "audit",
    help="Reconcile state: cek domain di CF tapi belum di Workspace (atau sebaliknya).",
)(audit_command)
app.command(
    "health",
    help="Check DNS health (MX/TXT/NS) of verified domains.",
)(health_command)
app.command(
    "check-expiry",
    help="Check domain expiry dates via RDAP. Alert domains expiring soon.",
)(check_expiry_command)
app.command(
    "dns-apply",
    help="Apply DNS records from YAML template ke domain(s).",
)(dns_apply_command)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"gsm {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_print_version,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        menu_command(ctx)


if __name__ == "__main__":
    app()
