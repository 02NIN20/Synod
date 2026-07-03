"""Ground-truth samples for benchmark: expected vulnerabilities per sample.

TP: finding with correct CWE AND line within ±2 lines of the real bug.
FP: finding that does not correspond to any ground-truth bug.
FN: ground-truth bug that no finding covers.
"""

GROUND_TRUTH = {
    "vulnerable_code.py": {
        "category": "security",
        "expected_cwes": {"CWE-798", "CWE-89", "CWE-78", "CWE-94"},
        "expected_count": 5,
        "note": "creds, SQLi, os.system, subprocess shell, eval",
    },
    "xss_app.py": {
        "category": "security",
        "expected_cwes": {"CWE-79"},
        "expected_count": 3,
        "note": "reflected XSS in greet, comment, search endpoints",
    },
    "path_traversal.py": {
        "category": "security",
        "expected_cwes": {"CWE-22"},
        "expected_count": 3,
        "note": "read_file, delete_file, serve_static without sanitization",
    },
    "csrf_missing.py": {
        "category": "security",
        "expected_cwes": {"CWE-352"},
        "expected_count": 2,
        "note": "transfer_money, change_email without CSRF token",
    },
    "insecure_deserialize.py": {
        "category": "security",
        "expected_cwes": {"CWE-502"},
        "expected_count": 3,
        "note": "pickle.loads x2, yaml.Loader",
    },
    "quality_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, only quality issues",
    },
    "coupling_sample.py": {
        "category": "quality",
        "expected_cwes": set(),
        "expected_count": 0,
        "note": "zero security vulns, tight coupling, deep nesting",
    },
}
