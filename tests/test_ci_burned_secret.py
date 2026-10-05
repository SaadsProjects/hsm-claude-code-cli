"""Tests for scripts/check_burned_secret.py.

The tests never contain the real burned value: they hash a made-up stand-in
and pass its digest in, the same way the script compares digests.
"""

import hashlib

from ci_scripts import load

check = load("check_burned_secret")

FAKE = "fake-burned-value-for-tests-0123"
FAKE_DIGEST = hashlib.sha256(FAKE.encode()).hexdigest()


def _scan(files, temporary=()):
    return check.scan(files, digest=FAKE_DIGEST, length=len(FAKE), temporary_exclusions=temporary)


def test_value_embedded_in_a_longer_token_fails():
    # The value inside a longer run of token characters must still be found.
    for text in (f'X="MOCK_{FAKE}"', f'X="{FAKE}_v2"', f"x{FAKE}y"):
        assert _scan({"a.py": text}) == ["a.py: contains the burned signing secret"], text


def test_files_without_a_known_suffix_are_scanned():
    files = {".claude/settings.local.json.example": FAKE, ".env.local": FAKE, "Dockerfile": FAKE}
    assert len(_scan(files)) == 3


def test_binary_files_are_skipped():
    assert check.is_binary(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert not check.is_binary(b"plain text\n")


def test_clean_tree_passes():
    assert _scan({"app.py": "SECRET = os.environ['X']\n"}) == []


def test_burned_value_in_source_fails():
    problems = _scan({"pkg/mod.py": f'_SECRET = b"{FAKE}"\n'})
    assert problems == ["pkg/mod.py: contains the burned signing secret"]


def test_burned_value_in_markdown_and_yaml_fails():
    problems = _scan({"docs/x.md": f"use {FAKE} here", ".github/workflows/a.yml": f"env: {{K: {FAKE}}}"})
    assert len(problems) == 2


def test_permanent_exclusions_are_skipped():
    files = {
        ".gitleaks.toml": FAKE,
        "aidlc/spaces/default/intents/261004-x/inception/evidence.md": FAKE,
    }
    assert _scan(files) == []


def test_record_tree_exclusion_is_limited_to_intents():
    problems = _scan({"aidlc/spaces/default/memory/team.md": FAKE})
    assert problems == ["aidlc/spaces/default/memory/team.md: contains the burned signing secret"]


def test_temporary_exclusion_skips_its_file():
    assert _scan({"mock_hsm/auth.py": f'b"{FAKE}"'}, temporary=("mock_hsm/auth.py",)) == []


def test_temporary_exclusion_that_outlived_the_literal_fails():
    problems = _scan({"mock_hsm/auth.py": "no secret here"}, temporary=("mock_hsm/auth.py",))
    assert problems == [
        "mock_hsm/auth.py: temporary exclusion no longer needed (the burned value is gone); "
        "remove it from TEMPORARY_EXCLUSIONS"
    ]


def test_temporary_exclusion_for_a_file_that_is_gone_fails():
    # Renamed or deleted: the exclusion must not linger unnoticed.
    problems = _scan({"other.py": "fine"}, temporary=("mock_hsm/auth.py",))
    assert problems == [
        "mock_hsm/auth.py: temporary exclusion names a file that is no longer tracked; "
        "remove it from TEMPORARY_EXCLUSIONS"
    ]


def test_candidates_are_every_window_of_the_value_length():
    assert check.candidates("abc de-g hi", length=5) == []
    assert check.candidates("x=abcdefg;", length=5) == ["abcde", "bcdef", "cdefg"]
    assert FAKE in check.candidates(f"pre_{FAKE}_post", length=len(FAKE))


def test_real_digest_constant_is_well_formed():
    assert len(check.BURNED_SECRET_SHA256) == 64
    int(check.BURNED_SECRET_SHA256, 16)
    assert check.BURNED_SECRET_LENGTH > 0
