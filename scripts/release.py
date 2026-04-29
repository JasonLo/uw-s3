# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "typer>=0.24.1",
#     "rich>=14.3.3",
# ]
# ///
import os
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

# typer is a PEP 723 script-level dep (see header), not a project dep,
# so the project's type checker can't resolve it.
import typer  # ty: ignore[unresolved-import]
from rich.console import Console

console = Console()
app = typer.Typer(help="Safe release manager for uw-s3.")

DEFAULT_BRANCH = "main"


def uv_env() -> dict[str, str]:
    """Strip VIRTUAL_ENV so `uv` targets the project venv, not this script's cache env."""
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}


class Increment(StrEnum):
    major = "major"
    minor = "minor"
    patch = "patch"
    alpha = "alpha"
    beta = "beta"
    rc = "rc"
    post = "post"
    dev = "dev"


class ReleaseError(Exception):
    pass


def run(cmd: list[str], capture: bool = True, env: dict[str, str] | None = None) -> str:
    """Run a command and return output, raising ReleaseError on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=capture, text=True, check=True, env=env
        )
        return result.stdout.strip() if capture else ""
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running {' '.join(cmd)}[/bold red]")
        if e.stderr:
            console.print(f"[red]{e.stderr.strip()}[/red]")
        raise ReleaseError(f"Command failed: {' '.join(cmd)}") from e


def best_effort(cmd: list[str], description: str) -> None:
    """Run a rollback command, surfacing stderr on failure but never raising."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[yellow]⚠️ {description} failed:[/yellow]")
        if result.stderr:
            console.print(f"[yellow]{result.stderr.strip()}[/yellow]")


def get_repo_root() -> Path:
    """Return the absolute path of the git repo root."""
    return Path(run(["git", "rev-parse", "--show-toplevel"]))


def get_push_target() -> tuple[str, str]:
    """Return (remote, branch) for pushing, derived from git config."""
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    try:
        remote = run(["git", "config", f"branch.{branch}.remote"])
    except ReleaseError:
        remote = "origin"
        console.print(
            "[yellow]⚠️ No tracking remote configured, defaulting to 'origin'.[/yellow]"
        )
    return remote, branch


def verify_git_state(remote: str) -> None:
    """Ensure the repo is clean and synced with remote."""
    console.print("🔍 [blue]Checking git status...[/blue]")

    # 1. Check for uncommitted changes (staged or unstaged)
    status = run(["git", "status", "--porcelain"])
    if status:
        console.print("[bold red]❌ Working directory is not clean![/bold red]")
        console.print("Please commit or stash your changes before releasing:")
        console.print(f"[yellow]{status}[/yellow]")
        raise ReleaseError("Working directory is not clean")

    # 2. Check if local is synced with remote
    run(["git", "fetch", remote])
    local_hash = run(["git", "rev-parse", "HEAD"])
    try:
        remote_hash = run(["git", "rev-parse", "@{u}"])
    except ReleaseError:
        console.print(
            "[yellow]⚠️ No upstream branch found. Skipping remote sync check.[/yellow]"
        )
        return

    if local_hash != remote_hash:
        ahead = run(["git", "rev-list", "HEAD", "--not", "@{u}", "--count"])
        behind = run(["git", "rev-list", "@{u}", "--not", "HEAD", "--count"])

        if int(behind) > 0:
            console.print(
                f"[bold red]❌ You are behind the remote by {behind} commits.[/bold red] Pull first."
            )
            raise ReleaseError(f"Behind remote by {behind} commits")
        if int(ahead) > 0:
            console.print(
                f"[bold red]❌ You have {ahead} unpushed commits.[/bold red] Push them first."
            )
            raise ReleaseError(f"Ahead of remote by {ahead} commits")

    console.print("[green]✅ Git state is clean and synced.[/green]")


def verify_quality() -> None:
    """Run lint and tests so we never tag a broken release."""
    console.print("🧹 [blue]Running ruff check...[/blue]")
    run(["uv", "run", "ruff", "check", "."], capture=False, env=uv_env())
    console.print("🧪 [blue]Running pytest...[/blue]")
    run(["uv", "run", "pytest"], capture=False, env=uv_env())
    console.print("[green]✅ Quality checks passed.[/green]")


@app.command()
def main(
    increment: Annotated[
        Increment, typer.Argument(help="Version component to bump")
    ] = Increment.patch,
) -> None:
    try:
        # Phase 1: Guards
        remote, branch = get_push_target()
        if branch != DEFAULT_BRANCH:
            console.print(
                f"[bold red]❌ Refusing to release from non-{DEFAULT_BRANCH} branch: {branch}[/bold red]"
            )
            raise ReleaseError(f"Releases must run from {DEFAULT_BRANCH}, not {branch}")

        # Operate from the repo root so all relative paths and uv commands
        # behave the same regardless of where the user invoked this script.
        os.chdir(get_repo_root())

        verify_git_state(remote)
        verify_quality()

        # Phase 2: Bump
        console.print(f"🚀 [blue]Bumping version ({increment.value})...[/blue]")
        run(["uv", "version", "--bump", increment.value], capture=False, env=uv_env())
        new_version: str = run(["uv", "version", "--short"], env=uv_env())
        tag_name: str = f"v{new_version}"

        # Phase 3: Commit and Tag
        console.print(f"📦 [blue]Creating tag {tag_name}...[/blue]")
        run(["git", "add", "pyproject.toml"])
        if Path("uv.lock").exists():
            run(["git", "add", "uv.lock"])
        run(["git", "commit", "-m", f"chore: release {tag_name}"], capture=False)
        run(["git", "tag", "-a", tag_name, "-m", tag_name], capture=False)

        # Phase 4: Push (atomic — branch and tag succeed or fail together)
        console.print(f"⬆️  [blue]Pushing to {remote}/{branch}...[/blue]")
        try:
            run(["git", "push", "--atomic", remote, branch, tag_name], capture=False)
        except ReleaseError:
            console.print(
                "[yellow]⚠️ Push failed — rolling back local commit and tag...[/yellow]"
            )
            best_effort(["git", "tag", "-d", tag_name], "Deleting local tag")
            best_effort(
                ["git", "reset", "--mixed", "HEAD~1"], "Reverting release commit"
            )
            raise

        # Phase 5: GitHub Release
        console.print(f"🐙 [blue]Creating GitHub release {tag_name}...[/blue]")
        try:
            run(
                [
                    "gh",
                    "release",
                    "create",
                    tag_name,
                    "--title",
                    tag_name,
                    "--generate-notes",
                ],
                capture=False,
            )
        except ReleaseError:
            console.print(
                f"[yellow]⚠️ The tag {tag_name} is already pushed. Re-run manually with:[/yellow]"
            )
            console.print(
                f"[yellow]  gh release create {tag_name} --title {tag_name} --generate-notes[/yellow]"
            )
            raise

        console.print(
            f"\n[bold green]✨ Successfully released {tag_name}![/bold green]"
        )

    except ReleaseError:
        sys.exit(1)


if __name__ == "__main__":
    app()
