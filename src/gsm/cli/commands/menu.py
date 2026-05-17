"""`gsm menu` - interactive menu for selecting features manually."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

MENU_ITEMS = [
    ("1", "Onboard domains", "gsm domains add"),
    ("2", "Create users (dari file akun.txt)", "gsm users add"),
    ("3", "Create users (auto-generate, tanpa file)", "gsm users gen"),
    ("4", "Reset password (bulk)", "gsm users reset-password"),
    ("5", "Suspend users", "gsm users suspend"),
    ("6", "Unsuspend users", "gsm users unsuspend"),
    ("7", "Audit: CF vs Workspace gap", "gsm audit"),
    ("8", "Health check DNS", "gsm health"),
    ("9", "Check domain expiry", "gsm check-expiry"),
    ("10", "List domains", "gsm domains list"),
    ("11", "List users", "gsm users list"),
    ("12", "Inactive user audit", "gsm users audit"),
    ("13", "Apply DNS template", "gsm dns-apply"),
    ("14", "Move users to OU", "gsm users move"),
    ("15", "Ledger stats", "gsm ledger stats"),
    ("16", "Doctor (health check config)", "gsm doctor"),
    ("0", "Exit", ""),
]


def menu_command(ctx: typer.Context) -> None:
    """Interactive menu - pilih fitur manual tanpa hafal command."""
    from gsm.cli import app as root_app

    while True:
        console.print(
            Panel.fit(
                _render_menu(),
                title="[bold cyan]gsm - Menu Utama[/bold cyan]",
                border_style="cyan",
            )
        )

        choice = Prompt.ask("\n[bold]Pilih nomor[/bold]", default="0").strip()

        if choice == "0":
            console.print("[dim]Bye![/dim]")
            break

        item = next((m for m in MENU_ITEMS if m[0] == choice), None)
        if item is None:
            console.print("[red]Pilihan gak valid. Coba lagi.[/red]\n")
            continue

        _, label, _cmd = item
        console.print(f"\n[bold green]▶ {label}[/bold green]\n")

        _run_submenu(choice, ctx, root_app)
        console.print()


def _render_menu() -> str:
    lines = []
    lines.append("[bold]Pilih fitur:[/bold]\n")
    for num, label, _ in MENU_ITEMS:
        if num == "0":
            lines.append(f"\n  [dim]{num}. {label}[/dim]")
        else:
            lines.append(f"  [cyan]{num:>2}[/cyan]. {label}")
    return "\n".join(lines)


def _run_submenu(choice: str, ctx: typer.Context, app: typer.Typer) -> None:
    """Dispatch menu choice to the appropriate interactive flow."""
    from pathlib import Path

    from rich.prompt import Confirm

    from gsm.cli._shared import get_context, read_lines, render_results

    if choice == "1":
        source = Prompt.ask(
            "File domain list atau ketik domain (comma-separated)",
            default="domains.txt",
        )
        path = Path(source)
        if path.exists():
            targets = read_lines(path)
        else:
            targets = [d.strip() for d in source.split(",") if d.strip()]
        if not targets:
            console.print("[yellow]Gak ada domain.[/yellow]")
            return
        console.print(f"[dim]{len(targets)} domain(s) akan di-onboard.[/dim]")
        if not Confirm.ask("Lanjut?", default=True):
            return
        runtime = get_context(ctx)
        from gsm.cli._shared import batch_progress
        from gsm.workflows.domain_onboarding import onboard_domains
        with batch_progress(f"Onboarding {len(targets)}", len(targets)) as on_progress:
            results = onboard_domains(
                targets, settings=runtime.settings, ledger=runtime.ledger,
                cf=runtime.cf, admin=runtime.admin, verify=runtime.verify,
                on_progress=on_progress,
            )
        render_results(results, title="Results")

    elif choice == "2":
        file_path = Prompt.ask("Path ke akun.txt", default="akun.txt")
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]File gak ketemu: {path}[/red]")
            return
        from gsm.workflows.user_bulk_create import create_users, parse_akun_file
        accounts = parse_akun_file(path)
        console.print(f"[dim]{len(accounts)} user(s) ditemukan.[/dim]")
        if not accounts or not Confirm.ask("Lanjut create?", default=True):
            return
        runtime = get_context(ctx)
        from gsm.cli._shared import batch_progress
        with batch_progress(f"Creating {len(accounts)}", len(accounts)) as on_progress:
            results = create_users(
                accounts, settings=runtime.settings, ledger=runtime.ledger,
                admin=runtime.admin, on_progress=on_progress,
            )
        render_results(results, title="Results")

    elif choice == "3":
        domain = Prompt.ask("Domain untuk generate users")
        count = int(Prompt.ask("Jumlah user", default="10"))
        pw_mode = Prompt.ask("Password", choices=["random", "sama"], default="random")
        fixed_pw = ""
        if pw_mode == "sama":
            fixed_pw = Prompt.ask("Password (sama untuk semua)")
        apply_now = Confirm.ask("Langsung create ke Workspace?", default=True)
        save_file = Prompt.ask("Save credentials ke file?", default="generated-creds.txt")

        args = ["users", "gen", "--domain", domain, "--count", str(count)]
        if fixed_pw:
            args.extend(["--fixed-password", fixed_pw])
        if apply_now:
            args.append("--apply")
        if save_file:
            args.extend(["--output", save_file])

        import subprocess
        import sys
        gsm_bin = str(Path(sys.executable).parent / "gsm")
        subprocess.run([gsm_bin, *args], check=False)

    elif choice == "4":
        domain = Prompt.ask("Domain (atau path ke file emails)")
        mode = Prompt.ask("Mode", choices=["same", "random"], default="random")
        runtime = get_context(ctx)
        path = Path(domain)
        if path.exists():
            emails = read_lines(path)
        else:
            from gsm.clients.google_admin import GoogleAdminError
            try:
                ws_users = runtime.admin.list_users(domain=domain)
            except GoogleAdminError as e:
                console.print(f"[red]{e}[/red]")
                return
            emails = [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
        if not emails:
            console.print("[yellow]Gak ada user.[/yellow]")
            return
        console.print(f"[dim]{len(emails)} user(s).[/dim]")
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        pw = ""
        if mode == "same":
            pw = Prompt.ask("Password baru")
        pw_results: list[tuple[str, str, bool]] = []
        from gsm.clients.google_admin import GoogleAdminError
        for email in emails:
            actual_pw = pw if mode == "same" else "".join(secrets.choice(alphabet) for _ in range(16))
            try:
                runtime.admin.update_password(email=email, password=actual_pw)
                pw_results.append((email, actual_pw, True))
            except GoogleAdminError as e:
                pw_results.append((email, "", False))
                console.print(f"[red][-] {email}: {e}[/red]")
        ok = sum(1 for _, _, s in pw_results if s)
        console.print(f"[green]Done: {ok}/{len(pw_results)} reset.[/green]")
        if mode == "random":
            save = Confirm.ask("Save credentials ke file?", default=True)
            if save:
                out = Path(Prompt.ask("Output file", default="new-creds.txt"))
                out.write_text("\n".join(f"{e} | {p}" for e, p, s in pw_results if s) + "\n")
                out.chmod(0o600)
                console.print(f"[green][+] Saved to {out}[/green]")

    elif choice == "5":
        domain = Prompt.ask("Domain untuk suspend semua user-nya")
        runtime = get_context(ctx)
        from gsm.clients.google_admin import GoogleAdminError
        try:
            ws_users = runtime.admin.list_users(domain=domain)
        except GoogleAdminError as e:
            console.print(f"[red]{e}[/red]")
            return
        emails = [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
        console.print(f"[dim]{len(emails)} user(s) akan di-suspend.[/dim]")
        if not Confirm.ask("Yakin?", default=False):
            return
        ok = 0
        for email in emails:
            try:
                runtime.admin.suspend_user(email)
                ok += 1
            except GoogleAdminError as e:
                console.print(f"[red][-] {email}: {e}[/red]")
        console.print(f"[green]Suspended {ok}/{len(emails)}.[/green]")

    elif choice == "6":
        domain = Prompt.ask("Domain untuk unsuspend semua user-nya")
        runtime = get_context(ctx)
        from gsm.clients.google_admin import GoogleAdminError
        try:
            ws_users = runtime.admin.list_users(domain=domain)
        except GoogleAdminError as e:
            console.print(f"[red]{e}[/red]")
            return
        emails = [u["primaryEmail"] for u in ws_users if u.get("primaryEmail")]
        ok = 0
        for email in emails:
            try:
                runtime.admin.unsuspend_user(email)
                ok += 1
            except GoogleAdminError as e:
                console.print(f"[red][-] {email}: {e}[/red]")
        console.print(f"[green]Unsuspended {ok}/{len(emails)}.[/green]")

    elif choice in ("7", "8", "9", "10", "11", "12", "13", "14", "15", "16"):
        _dispatch_via_subprocess(choice)


def _dispatch_via_subprocess(choice: str) -> None:
    """Run gsm subcommands via subprocess for proper signal/exit handling."""
    import subprocess
    import sys

    cmd_map = {
        "7": ["audit"],
        "8": ["health"],
        "9": ["check-expiry"],
        "10": ["domains", "list"],
        "11": ["users", "list"],
        "12": ["users", "audit"],
        "13": ["dns-apply"],
        "14": ["users", "move"],
        "15": ["ledger", "stats"],
        "16": ["doctor"],
    }
    args = list(cmd_map[choice])
    if choice == "13":
        tpl = Prompt.ask("Path ke YAML template")
        args.append(tpl)
    elif choice == "14":
        ou = Prompt.ask("OU path (e.g. /Sales)")
        domain = Prompt.ask("Domain")
        args.extend(["--ou", ou, "--domain", domain])
    elif choice == "12":
        days = Prompt.ask("Inactive days threshold", default="30")
        args.extend(["--inactive-days", days])

    gsm_bin = str(Path(sys.executable).parent / "gsm")
    subprocess.run([gsm_bin, *args], check=False)
