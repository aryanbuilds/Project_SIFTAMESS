"""Shared pytest fixtures for Epic A tests."""

from __future__ import annotations

import pytest
import typer
from siftmesh_core.cli import app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    # Do NOT pass mix_stderr= — removed in Typer 0.16+ (Click 8.2 alignment).
    return CliRunner()


@pytest.fixture
def cli_app() -> typer.Typer:
    return app
