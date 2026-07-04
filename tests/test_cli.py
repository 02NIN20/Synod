"""Tests for the Synod CLI using Typer's CliRunner."""

from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


def test_health_fails_when_offline():
    result = runner.invoke(app, ["health", "--url", "http://localhost:1"])
    assert result.exit_code == 1
    assert "Synod unreachable" in result.stdout


def test_review_file_not_found():
    result = runner.invoke(app, ["review", "nonexistent.py"])
    assert result.exit_code == 1
    assert "File not found" in result.stdout


def test_help_review_shows_options():
    result = runner.invoke(app, ["review", "--help"])
    assert result.exit_code == 0
    assert "FILEPATH" in result.stdout
    assert "--fix" in result.stdout
    assert "--show-code" in result.stdout


def test_help_health_shows_options():
    result = runner.invoke(app, ["health", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.stdout
