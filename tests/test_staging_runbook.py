"""The staging app runbook, docs/staging-app.md (unit U6, plan S3).

Creating the staging app is the owner's console work, so the repository holds
only the runbook. These tests keep it in step with the code: every secret key
the dashboard reads (from .streamlit/secrets.toml.example, contract C7), the
app's main file and branch, the post-deploy check command (contract C8) and
the OAuth redirect path. Python 3.10 has no tomllib, so key names come from a
line pattern that also picks up the commented-out HSM_SIGNING_SECRET.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = ROOT / "docs" / "staging-app.md"
SECRETS_EXAMPLE = ROOT / ".streamlit" / "secrets.toml.example"

KEY_LINE = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)
EXPECTED_KEYS = {
    "HSM_SIGNING_SECRET",
    "HSM_ALLOWED_EMAILS",
    "redirect_uri",
    "cookie_secret",
    "client_id",
    "client_secret",
    "server_metadata_url",
}


def secret_keys(path):
    """Key names assigned in a secrets TOML file, commented-out ones included."""
    return set(KEY_LINE.findall(path.read_text()))


def runbook():
    return RUNBOOK.read_text()


def paragraphs(text):
    return [block for block in re.split(r"\n\s*\n", text) if block.strip()]


def test_runbook_exists():
    assert RUNBOOK.is_file()
    assert runbook().strip()


def test_key_reader_returns_the_seven_keys_from_the_example():
    assert secret_keys(SECRETS_EXAMPLE) == EXPECTED_KEYS


def test_key_reader_handles_commented_tables_and_prose(tmp_path):
    sample = tmp_path / "secrets.toml"
    sample.write_text(
        "# A comment with no assignment\n"
        '# COMMENTED_KEY = "x"\n'
        'TOP = ["a"]\n'
        "[auth]\n"
        '  indented_key = "y"\n'
        'not a key = "z"\n'
    )
    assert secret_keys(sample) == {"COMMENTED_KEY", "TOP", "indented_key"}


@pytest.mark.parametrize("key", sorted(secret_keys(SECRETS_EXAMPLE)))
def test_runbook_names_every_secret_key(key):
    assert f"`{key}`" in runbook() or f"{key} =" in runbook()


def test_runbook_says_signing_and_cookie_secrets_differ():
    matching = [
        block
        for block in paragraphs(runbook())
        if "HSM_SIGNING_SECRET" in block
        and "cookie_secret" in block
        and re.search(r"\bdiffer|\bnever the same\b|\bnot the same\b", block)
    ]
    assert matching, "no paragraph says HSM_SIGNING_SECRET and cookie_secret must differ"


def test_runbook_names_the_main_file_and_branch():
    text = runbook()
    assert "`dashboard/app.py`" in text
    assert re.search(r"[Bb]ranch[^\n]*`main`", text)


def test_runbook_gives_the_postdeploy_command_and_redirect_path():
    text = runbook()
    assert re.search(r"python3 scripts/postdeploy_check\.py https://<staging-app>\.streamlit\.app\b", text)
    assert "https://<staging-app>.streamlit.app/oauth2callback" in text


def section_start(text, heading_words):
    match = re.search(rf"^## [^\n]*{heading_words}", text, re.MULTILINE)
    assert match, f"no section heading containing {heading_words!r}"
    return match.start()


def test_runbook_makes_the_refused_account_a_test_user_too():
    # In testing mode Google blocks any account that isn't a test user before it
    # reaches the app, so the refusal proof (step d) needs that account listed.
    matching = [
        block
        for block in paragraphs(runbook())
        if re.search(r"test users?\b", block) and re.search(r"not on the allowlist|step \(d\)|second account", block)
    ]
    assert matching, "the runbook doesn't make the not-allowlisted account a test user"


def test_runbook_times_the_check_from_a_sleeping_app():
    text = runbook()
    assert re.search(r"time python3 scripts/postdeploy_check\.py https://<staging-app>\.streamlit\.app\b", text)
    assert re.search(r"sleep", text, re.IGNORECASE)
    assert re.search(r"30 seconds", text)


def test_runbook_generates_the_secrets_before_creating_the_app():
    text = runbook()
    assert text.index("token_urlsafe") < section_start(text, "Create the app")


def test_runbook_secrets_block_has_the_c7_layout():
    block = re.search(r"```toml\n(.*?)```", runbook(), re.DOTALL)
    assert block, "no fenced toml block"
    toml = block.group(1)

    def at(token):
        assert token in toml, token
        return toml.index(token)

    auth, google = at("[auth]\n"), at("[auth.google]")
    assert at("HSM_SIGNING_SECRET =") < auth
    assert at("HSM_ALLOWED_EMAILS =") < auth
    assert auth < at("redirect_uri =") < google
    assert auth < at("cookie_secret =") < google
    for key in ("client_id =", "client_secret =", "server_metadata_url ="):
        assert google < at(key)


def test_runbook_secrets_block_holds_exactly_the_example_keys():
    # Naming a key in prose isn't enough: the block is what the owner pastes.
    block = re.search(r"```toml\n(.*?)```", runbook(), re.DOTALL)
    assert block, "no fenced toml block"
    assert set(KEY_LINE.findall(block.group(1))) == secret_keys(SECRETS_EXAMPLE)


def test_runbook_says_when_to_set_hosted_python():
    # CI tests the hosted Python only when the HOSTED_PYTHON variable names it.
    matching = [
        block for block in paragraphs(runbook()) if "HOSTED_PYTHON" in block and re.search(r"Python version", block)
    ]
    assert matching, "the runbook doesn't tie the chosen Python version to HOSTED_PYTHON"


def test_runbook_checks_a_later_merge_redeploys_staging():
    matching = [
        block
        for block in paragraphs(runbook())
        if re.search(r"redeploy", block, re.IGNORECASE) and "Build" in block and re.search(r"merge", block)
    ]
    assert matching, "no step confirms that a later merge to main redeploys staging"


def test_runbook_uses_placeholders_only():
    text = runbook()
    emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    assert set(emails) <= {"your-email@example.com"}, emails
    assert ".apps.googleusercontent.com" not in text
    assert not re.search(r"https://(?!<)[\w-]+\.streamlit\.app", text), "a real app URL is in the runbook"
