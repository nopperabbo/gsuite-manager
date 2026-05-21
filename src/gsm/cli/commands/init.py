"""`gsm setup` - interactive setup wizard for first-time users.

Designed for non-engineers. Holds the user's hand through:
  1. Welcome + check what's missing
  2. Cloudflare API token (with link to dashboard + scope hints)
  3. Cloudflare Account ID (with auto-detect helper)
  4. Google OAuth Desktop App credentials (with link to GCP guide)
  5. Test connections live
  6. Save .env atomically with mode 0o600

Non-interactive scaffold mode preserved as `gsm init` (legacy behavior).
"""

from __future__ import annotations

import re
from pathlib import Path

import typer
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from gsm.cli._shared import console, err_console
from gsm.core.auth import detect_oauth_client_file

__all__ = ["init_command", "setup_command"]

CF_DASHBOARD_URL = "https://dash.cloudflare.com/profile/api-tokens"
GCP_OAUTH_GUIDE_URL = "https://console.cloud.google.com/apis/credentials"
DOCS_GCP_GUIDE = "docs/SETUP_GOOGLE_OAUTH.md"


def setup_command(
    cwd: Path | None = typer.Option(
        None,
        "--cwd",
        help="Folder tempat .env akan disimpan (default: folder sekarang).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Timpa .env yang sudah ada."
    ),
    skip_test: bool = typer.Option(
        False,
        "--skip-test",
        help="Lewati test koneksi live (offline mode).",
    ),
) -> None:
    """Wizard interaktif untuk setup awal. Cocok untuk non-engineer."""
    target = (cwd or Path.cwd()).resolve()
    env_path = target / ".env"

    _print_welcome(target)

    if env_path.exists() and not force and not Confirm.ask(
        f"\n[yellow].env sudah ada di {env_path}.[/yellow] "
        "Mau timpa dengan setting baru?",
        default=False,
    ):
        console.print("[dim]Batal. Gak ada perubahan.[/dim]")
        raise typer.Exit(code=0)

    cf_token = _ask_cf_token()
    cf_account_id = _ask_cf_account_id(cf_token, skip_test=skip_test)
    oauth_path = _ask_oauth_client(target)

    if not skip_test:
        _test_cf_connection(cf_token)

    settings = {
        "GSM_CF_API_TOKEN": cf_token,
        "GSM_CF_ACCOUNT_ID": cf_account_id,
        "GSM_GOOGLE_OAUTH_CLIENT_PATH": str(oauth_path),
        "GSM_GOOGLE_OAUTH_TOKEN_PATH": "./token.json",
    }
    _write_env(env_path, settings)

    _print_summary(env_path, oauth_path)


def init_command(
    cwd: Path | None = typer.Option(
        None,
        "--cwd",
        help="Working directory to scaffold (default: current).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing .env (DANGEROUS)."
    ),
) -> None:
    """Non-interaktif: tulis .env template kosong (untuk power user/CI)."""
    target = (cwd or Path.cwd()).resolve()
    env_path = target / ".env"

    if env_path.exists() and not force:
        console.print(
            f"[yellow][!][/yellow] {env_path} already exists. Use --force to overwrite."
        )
    else:
        env_path.write_text(_ENV_TEMPLATE, encoding="utf-8")
        env_path.chmod(0o600)
        console.print(f"[green][+][/green] Wrote {env_path}")

    oauth_file = detect_oauth_client_file(target)
    if oauth_file is None:
        err_console.print(
            "[red][-][/red] No OAuth client file found "
            "(`credentials.json` or `client_secret_*.json`)."
        )
    else:
        console.print(f"[green][+][/green] OAuth client detected: {oauth_file.name}")

    console.print(
        Panel.fit(
            "[bold]Next steps[/bold]\n\n"
            "1. Edit [cyan].env[/cyan] - set "
            "[cyan]GSM_CF_API_TOKEN[/cyan] and [cyan]GSM_CF_ACCOUNT_ID[/cyan].\n"
            "2. Place OAuth credentials JSON as [cyan]credentials.json[/cyan].\n"
            "3. Run [cyan]gsm doctor[/cyan] to verify setup.\n"
            "4. Run [cyan]gsm domains add example.com[/cyan] to start.\n\n"
            "[dim]Tip: untuk wizard interaktif, pakai [cyan]gsm setup[/cyan] saja.[/dim]",
            title="gsm init",
            border_style="cyan",
        )
    )


def _print_welcome(target: Path) -> None:
    console.print(
        Panel.fit(
            Text.from_markup(
                "[bold cyan]Selamat datang di gsuite-manager setup wizard![/bold cyan]\n\n"
                "Wizard ini bakal nanya 3 hal:\n"
                "  1. Cloudflare API Token (buat manage DNS)\n"
                "  2. Cloudflare Account ID (auto-detect dari token)\n"
                "  3. Lokasi file OAuth Google Workspace\n\n"
                f"Settingan disimpan di: [yellow]{target}/.env[/yellow]\n"
                "[dim]Cancel kapan saja dengan Ctrl+C.[/dim]"
            ),
            title="gsm setup",
            border_style="cyan",
        )
    )


def _ask_cf_token() -> str:
    console.print(
        "\n[bold cyan]Step 1/3:[/bold cyan] Cloudflare API Token\n"
    )
    console.print(
        f"  Buat token baru di: [link={CF_DASHBOARD_URL}]{CF_DASHBOARD_URL}[/link]\n"
        "  Pilih template [cyan]'Edit zone DNS'[/cyan], scope ke [cyan]All zones[/cyan].\n"
        "  Token cuma muncul sekali - copy & paste cepet ke sini.\n"
    )
    while True:
        token = Prompt.ask("  CF API Token", password=True).strip()
        if len(token) < 30:
            err_console.print(
                "[red]  [-] Token kependekan (CF token biasanya 40+ karakter). "
                "Coba lagi.[/red]"
            )
            continue
        return token


def _ask_cf_account_id(token: str, *, skip_test: bool) -> str:
    console.print(
        "\n[bold cyan]Step 2/3:[/bold cyan] Cloudflare Account ID\n"
    )

    if not skip_test:
        detected = _try_autodetect_account_id(token)
        if detected:
            console.print(
                f"  [green][+][/green] Auto-detect dari token: [cyan]{detected}[/cyan]"
            )
            if Confirm.ask("  Pakai ini?", default=True):
                return detected

    console.print(
        "  Cara cari Account ID:\n"
        f"  1. Buka: [link={CF_DASHBOARD_URL.rsplit('/', 2)[0]}]"
        "https://dash.cloudflare.com[/link]\n"
        "  2. Klik domain manapun yang lo punya\n"
        "  3. Scroll kanan-bawah - 'Account ID' tertera (32 karakter hex)\n"
    )
    while True:
        account_id = Prompt.ask("  CF Account ID").strip().lower()
        if not re.match(r"^[a-f0-9]{32}$", account_id):
            err_console.print(
                "[red]  [-] Format salah. Account ID = 32 karakter hex (a-f, 0-9). "
                "Coba lagi.[/red]"
            )
            continue
        return account_id


def _ask_oauth_client(target: Path) -> Path:
    console.print(
        "\n[bold cyan]Step 3/3:[/bold cyan] Google OAuth Desktop App credentials\n"
    )

    detected = detect_oauth_client_file(target)
    if detected is not None:
        console.print(
            f"  [green][+][/green] Ketemu file OAuth: [cyan]{detected.name}[/cyan]"
        )
        if Confirm.ask("  Pakai ini?", default=True):
            return Path(detected.name) if detected.parent == target else detected

    console.print(
        f"  Belum ada file OAuth Desktop App di {target}.\n"
        f"  Cara dapetnya - lihat [cyan]{DOCS_GCP_GUIDE}[/cyan]\n"
        f"  atau buka: [link={GCP_OAUTH_GUIDE_URL}]{GCP_OAUTH_GUIDE_URL}[/link]\n"
        "  (bikin project → enable Admin SDK + Site Verification → "
        "OAuth client ID → Desktop app → download JSON)\n\n"
        "  [yellow][!] Skip dulu kalau belum siap - bisa drop file-nya nanti."
        "[/yellow]\n"
    )

    while True:
        path_str = Prompt.ask(
            "  Path ke file credentials JSON",
            default="./credentials.json",
        ).strip()
        path = Path(path_str)
        if path.is_absolute() or path_str.startswith("./"):
            return path
        return Path("./" + path_str)


def _try_autodetect_account_id(token: str) -> str | None:
    try:
        import requests

        resp = requests.get(
            "https://api.cloudflare.com/client/v4/accounts",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        data = resp.json()
        if data.get("success") and data.get("result"):
            results = data["result"]
            if len(results) == 1:
                return str(results[0].get("id"))
    except Exception:
        return None
    return None


def _test_cf_connection(token: str) -> None:
    console.print("\n[dim]Test koneksi ke Cloudflare...[/dim]")
    try:
        import requests

        resp = requests.get(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        data = resp.json()
        if data.get("success"):
            status = data.get("result", {}).get("status", "active")
            console.print(
                f"[green][+][/green] CF token VALID (status: {status})"
            )
        else:
            errs = "; ".join(
                e.get("message", "?") for e in data.get("errors", [])
            )
            err_console.print(f"[red][-][/red] CF token INVALID: {errs}")
            err_console.print(
                "[yellow]  Setting tetap disimpan, tapi `gsm doctor` "
                "bakal fail di check Cloudflare.[/yellow]"
            )
    except Exception as e:
        err_console.print(f"[yellow][!][/yellow] Test koneksi gagal: {e}")


def _write_env(env_path: Path, user_values: dict[str, str]) -> None:
    lines = _ENV_TEMPLATE.splitlines()
    out: list[str] = []
    for line in lines:
        replaced = False
        for key, value in user_values.items():
            if line.startswith(f"{key}="):
                out.append(f"{key}={value}")
                replaced = True
                break
        if not replaced:
            out.append(line)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    env_path.chmod(0o600)


def _print_summary(env_path: Path, oauth_path: Path) -> None:
    oauth_exists = (env_path.parent / oauth_path).exists() if not oauth_path.is_absolute() else oauth_path.exists()
    oauth_status = "[green]ada[/green]" if oauth_exists else "[yellow]belum ada[/yellow]"

    console.print(
        Panel.fit(
            "[bold green][+] Setup selesai![/bold green]\n\n"
            f"  Settings: [cyan]{env_path}[/cyan]\n"
            f"  OAuth file: [cyan]{oauth_path}[/cyan] ({oauth_status})\n\n"
            "[bold]Next:[/bold]\n"
            "  1. [cyan]gsm doctor[/cyan] - verify semua siap\n"
            "  2. [cyan]gsm domains add domain-test.com[/cyan] - coba 1 domain\n"
            "  3. Kalo OK, [cyan]gsm domains add --file domains.txt[/cyan] - bulk\n",
            title="Selesai",
            border_style="green",
        )
    )


_ENV_TEMPLATE = """\
# gsuite-manager configuration. All keys prefixed GSM_.
# This file MUST stay out of version control.

# --- Cloudflare ---
GSM_CF_API_TOKEN=
GSM_CF_ACCOUNT_ID=

# --- Google OAuth (Desktop App) ---
GSM_GOOGLE_OAUTH_CLIENT_PATH=./credentials.json
GSM_GOOGLE_OAUTH_TOKEN_PATH=./token.json

# --- Throttling (sequential by default, anti rate-limit) ---
GSM_DELAY_PER_DOMAIN_SEC=3
GSM_DELAY_PER_USER_SEC=1

# --- DNS propagation pre-check (fixes 271-failure race) ---
GSM_DNS_CHECK_RESOLVERS=8.8.8.8,1.1.1.1
GSM_DNS_CHECK_TIMEOUT_SEC=5
GSM_DNS_CHECK_MAX_ATTEMPTS=8
GSM_DNS_CHECK_BACKOFF_SEC=10,20,30,45,60,60,90,120

# --- State + Logging ---
GSM_LEDGER_PATH=./gsm_state.json
GSM_LOG_LEVEL=INFO
GSM_LOG_FORMAT=console
"""
