"""Command-line entry point: ``handrail <group> <command>``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from handrail.config import get_settings
from handrail.schema import ArtifactError, approve, load_artifact
from handrail.schema.io import dump_artifact
from handrail.schema.jsonschema import stale_schemas, write_schemas

app = typer.Typer(no_args_is_help=True, help="Discover once with an LLM, replay deterministically.")
schema_app = typer.Typer(no_args_is_help=True, help="Published JSON Schema documents.")
artifact_app = typer.Typer(no_args_is_help=True, help="Validate and approve capability artifacts.")
app.add_typer(schema_app, name="schema")
app.add_typer(artifact_app, name="artifact")

PathArg = Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]


@schema_app.command("export")
def schema_export() -> None:
    """Regenerate the JSON Schema files from the models."""
    for path in write_schemas(get_settings().schema_dir):
        typer.echo(f"wrote {path}")


@schema_app.command("check")
def schema_check() -> None:
    """Fail if the committed JSON Schema files are out of date."""
    stale = stale_schemas(get_settings().schema_dir)
    if stale:
        typer.echo(
            f"stale schema files: {', '.join(stale)}; run 'handrail schema export'", err=True
        )
        raise typer.Exit(1)
    typer.echo("schema files are current")


@artifact_app.command("validate")
def artifact_validate(path: PathArg) -> None:
    """Validate an artifact against the schema and its content hash."""
    try:
        artifact = load_artifact(path)
    except ArtifactError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"ok {artifact.ref} ({artifact.status})")


@artifact_app.command("approve")
def artifact_approve(
    path: PathArg, reviewer: Annotated[str, typer.Option(help="Who reviewed it.")]
) -> None:
    """Approve a draft in place: set status, reviewer and content hash."""
    try:
        approved = approve(load_artifact(path), reviewer=reviewer, at=datetime.now(UTC))
    except ArtifactError as exc:
        typer.echo(f"cannot approve: {exc}", err=True)
        raise typer.Exit(1) from exc
    path.write_text(dump_artifact(approved), encoding="utf-8")
    typer.echo(f"approved {approved.ref} {approved.content_hash}")


if __name__ == "__main__":
    app()
