"""Semgrep pre-filter for security findings.

Runs Semgrep on a temporary file and returns raw findings. Gracefully
degrades to an empty list if semgrep is unavailable, times out, or
returns no results.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Any

from app.models.schemas import AgentRole, Finding, FindingSource, Severity

logger = logging.getLogger("synod.semgrep")

DEFAULT_RULES = [
    "p/security-audit",
    "p/owasp-top-ten",
    "p/cwe-top-25",
    "app/tools/semgrep_rules.yml",
]

SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}

CWE_MAP = {
    "synod.path-traversal-user-input": "CWE-22",
    "synod.command-injection": "CWE-78",
    "synod.sql-injection": "CWE-89",
    "synod.code-injection": "CWE-94",
    "synod.insecure-deserialization": "CWE-502",
    "synod.hardcoded-secret": "CWE-798",
    "synod.missing-csrf": "CWE-352",
    "synod.reflected-xss": "CWE-79",
}


def _severity(rule_severity: str) -> str:
    return SEVERITY_MAP.get(rule_severity.upper(), "medium")


def _find_semgrep_cmd() -> list[str]:
    """Return the best available semgrep invocation.

    Prefers the `semgrep` binary (works in containers and venvs when PATH
    is set), then the binary next to the current Python executable, then
    `python -m semgrep` as a last resort.
    """
    binary = shutil.which("semgrep")
    if binary:
        return [binary]
    venv_binary = os.path.join(sys.exec_prefix, "bin", "semgrep")
    if os.path.isfile(venv_binary):
        return [venv_binary]
    return [sys.executable, "-m", "semgrep"]


def run_semgrep(code: str, filename: str, timeout: int = 60) -> list[dict[str, Any]]:
    """Run semgrep on `code` and return a list of raw findings.

    Returns empty list on any failure so the pipeline never breaks.
    """
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{os.path.basename(filename or 'snippet.py')}", delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        cmd = _find_semgrep_cmd()
        for rule in DEFAULT_RULES:
            cmd += ["--config", rule]
        cmd += [
            "--json",
            "--quiet",
            "--disable-version-check",
            "--metrics",
            "off",
            tmp_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("semgrep not installed; skipping pre-filter")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("semgrep timed out after %ss; skipping pre-filter", timeout)
        return []
    except Exception as e:  # pragma: no cover - broad safety net
        logger.warning("semgrep failed: %s; skipping pre-filter", e)
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if result.returncode not in (0, 1):
        # return code 0 = no findings, 1 = findings, >1 = error
        logger.warning("semgrep exited with code %s: %s", result.returncode, result.stderr[:200])
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("semgrep returned invalid JSON")
        return []

    findings = []
    for r in data.get("results", []):
        finding = {
            "rule_id": r.get("check_id", "unknown"),
            "line": r.get("start", {}).get("line", 0),
            "message": r.get("extra", {}).get("message", ""),
            "severity": _severity(r.get("extra", {}).get("severity", "WARNING")),
            "path": r.get("path", ""),
            "metadata": r.get("extra", {}).get("metadata", {}),
        }
        findings.append(finding)

    logger.info("semgrep found %s findings", len(findings))
    return findings


def findings_to_model(raw_findings: list[dict[str, Any]]) -> list[Finding]:
    """Convert raw semgrep findings into Synod Finding objects."""
    severity_map = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    result = []
    for raw in raw_findings:
        rule_id = raw.get("rule_id", "unknown")
        cwe = CWE_MAP.get(rule_id, "")
        line = raw.get("line", 0)
        impact = severity_map.get(raw.get("severity", "medium").lower(), Severity.MEDIUM)
        title = rule_id.split(".")[-1].replace("-", " ").title()
        result.append(Finding(
            id=str(uuid.uuid4()),
            agent=AgentRole.SENTINEL,
            title=f"Semgrep: {title}",
            detail=f"{raw.get('message', '')} (line {line})",
            impact=impact,
            line_number=line,
            cwe=cwe,
            confidence=0.95,
            source=FindingSource.SEMGREP,
        ))
    return result
