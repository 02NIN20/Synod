"""Ground-truth samples for benchmark: expected vulnerabilities per sample."""

GROUND_TRUTH = {
    "vulnerable_code": {
        "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"},
        "expected_count": 5,
        "note": "creds, SQLi, os.system, subprocess shell, eval",
    },
    "quality_sample": {
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, only quality issues",
    },
}
