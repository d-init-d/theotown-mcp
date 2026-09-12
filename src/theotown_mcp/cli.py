"""
Typer Command-Line Interface (CLI) for TheoTown MCP Server.
Provides subcommands:
- probe-ipc: Validates storage persistence, .pmodext, SharedPreferences, and telemetry IPC.
- install-plugin: Installs or symlinks the Lua plugin into %USERPROFILE%\\TheoTown\\plugins\\theotown_mcp\\.
- run: Launches the MCP server over stdio or streamable-http.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

from theotown_mcp.bridge import get_bridge, write_atomic_lua
from theotown_mcp.config import get_config
from theotown_mcp.server import create_server

app = typer.Typer(
    name="theotown-mcp",
    help="TheoTown MCP Server CLI — Autonomous AI City Planning & Construction",
    add_completion=False,
    no_args_is_help=True,
)


@app.command("probe-ipc")
def probe_ipc(
    data_dir: Annotated[str | None, typer.Option("--data-dir", "-d", help="Override TheoTown data directory")] = None,
) -> None:
    """Execute storage and telemetry ground-truth probe on local TheoTown installation."""
    typer.echo("[*] Probing TheoTown installation and IPC channels...")
    config = get_config(data_dir_override=data_dir)

    typer.echo(f"[*] TheoTown data directory: {config.theotown_data_dir}")
    if config.is_installed():
        typer.secho(f"  [+] Data directory exists: {config.theotown_data_dir}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"  [-] Data directory not found: {config.theotown_data_dir}", fg=typer.colors.YELLOW)

    # 1. Inspect .pmodext
    pmodext_path = config.pmodext_path
    if pmodext_path.exists():
        try:
            raw = pmodext_path.read_text(encoding="utf-8", errors="replace")
            size = pmodext_path.stat().st_size
            has_hash = "#" in raw
            typer.secho(f"  [+] .pmodext found ({size} bytes, delimiter '#': {has_hash})", fg=typer.colors.GREEN)
        except (OSError, UnicodeDecodeError) as exc:
            typer.secho(f"  [-] Error reading .pmodext: {exc}", fg=typer.colors.RED)
    else:
        typer.echo(f"  [*] .pmodext not yet created at: {pmodext_path}")

    # 2. Inspect SharedPreferences
    prefs_dir = config.prefs_dir
    if prefs_dir.exists():
        pref_files = list(prefs_dir.glob("*"))
        typer.secho(f"  [+] TheoTown .prefs directory exists ({len(pref_files)} files found)", fg=typer.colors.GREEN)
    else:
        typer.echo(f"  [*] Preferences directory not found at: {prefs_dir}")

    # 3. Test Atomic Bridge Write
    test_target = config.plugin_dir / "probe_test.tmp"
    try:
        config.ensure_directories()
        write_atomic_lua(test_target, "-- probe canary write\nreturn true\n")
        if test_target.exists():
            test_target.unlink()
            typer.secho("  [+] Atomic filesystem write test: PASS", fg=typer.colors.GREEN)
    except (OSError, PermissionError) as exc:
        typer.secho(f"  [-] Atomic filesystem write test failed: {exc}", fg=typer.colors.YELLOW)

    # 4. Check Telemetry
    bridge = get_bridge(config)
    telemetry = bridge.read_telemetry()
    if telemetry.connected:
        typer.secho(
            f"  [+] Live city telemetry detected: '{telemetry.name}' | "
            f"Population: {telemetry.population} | Funds: {telemetry.money} Theons | "
            f"Grid: {telemetry.width}x{telemetry.height} | Speed: {telemetry.speed}",
            fg=typer.colors.GREEN,
        )
    else:
        typer.echo("  [*] Live telemetry file not detected or game not running (offline fallback active)")

    typer.secho("[+] Probe IPC diagnostics completed successfully.", fg=typer.colors.GREEN)


@app.command("install-plugin")
def install_plugin(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing plugin files")] = False,
    symlink: Annotated[bool, typer.Option("--symlink", "-s", help="Create directory symlink instead of copying")] = False,
    data_dir: Annotated[str | None, typer.Option("--data-dir", "-d", help="Override TheoTown data directory")] = None,
) -> None:
    """Install the TheoTown MCP Lua plugin into %USERPROFILE%\\TheoTown\\plugins\\theotown_mcp\\."""
    config = get_config(data_dir_override=data_dir)
    target_dir = config.plugin_dir

    typer.echo(f"[*] Installing Lua plugin assets (force={force}, symlink={symlink})...")
    typer.echo(f"[*] Target destination: {target_dir}")

    # Locate source plugin directory
    candidate_sources = [
        Path(__file__).resolve().parent.parent.parent / "plugin" / "theotown_mcp",
        Path.cwd() / "plugin" / "theotown_mcp",
    ]
    source_dir: Path | None = None
    for cand in candidate_sources:
        if cand.exists() and cand.is_dir():
            source_dir = cand
            break

    if source_dir is None:
        typer.secho(
            "[-] Error: Could not locate source plugin directory in repository ('plugin/theotown_mcp').",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    if target_dir.exists():
        if not force:
            typer.secho(
                f"[-] Warning: Destination {target_dir} already exists. Use --force to overwrite.",
                fg=typer.colors.YELLOW,
            )
            return
        if target_dir.is_symlink():
            target_dir.unlink()
        elif target_dir.is_dir():
            shutil.rmtree(target_dir)

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if symlink:
        try:
            os.symlink(source_dir, target_dir, target_is_directory=True)
            typer.secho(f"[+] Successfully symlinked plugin from {source_dir} to {target_dir}", fg=typer.colors.GREEN)
            return
        except OSError as exc:
            typer.secho(f"[-] Symlink failed ({exc}). Falling back to directory copy...", fg=typer.colors.YELLOW)

    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
    typer.secho(f"[+] Successfully installed plugin to {target_dir}", fg=typer.colors.GREEN)


@app.command("run")
def run_server(
    transport: Annotated[str, typer.Option("--transport", "-t", help="Transport mode: stdio or http")] = "stdio",
    host: Annotated[str, typer.Option("--host", "-h", help="Bind host for HTTP transport")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port for HTTP transport")] = 8000,
) -> None:
    """Launch the TheoTown Model Context Protocol server."""
    if transport not in ("stdio", "http", "streamable-http"):
        typer.secho(
            f"Error: Unknown transport '{transport}'. Choose 'stdio' or 'http'.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    server = create_server()

    if transport == "stdio":
        typer.echo("[*] Starting TheoTown MCP Server on STDIO transport...")
        server.run(transport="stdio")
    elif transport in ("http", "streamable-http"):
        typer.echo(f"[*] Starting TheoTown MCP Server on Streamable HTTP transport ({host}:{port}/mcp)...")
        server.run(transport="streamable-http", host=host, port=port)


def main() -> None:
    """Main CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
