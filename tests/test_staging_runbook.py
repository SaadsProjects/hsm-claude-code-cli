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
from ci_scripts import load

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


def test_runbook_covers_the_organizations_oauth_app_restriction():
    # The first staging deploy failed until the org owner granted Streamlit access.
    matching = [
        block
        for block in paragraphs(runbook())
        if "OAuth" in block and re.search(r"organi[sz]ation", block) and re.search(r"\bGrant\b", block)
    ]
    assert matching, "the runbook doesn't say how to approve Streamlit for a restricted organization"


def test_runbook_says_what_closes_the_two_open_proof_items():
    blocks = paragraphs(runbook())
    timing = [b for b in blocks if "NFR2" in b and re.search(r"\bstays open\b", b) and "closes" in b]
    assert timing, "the timing paragraph doesn't say what closes NFR2 or that it stays open until then"
    redeploy = [b for b in blocks if "redeploys" in b and "first merge after the app exists" in b]
    assert redeploy, "step (e) doesn't say which merge closes it"


def test_runbook_checks_a_later_merge_redeploys_staging():
    matching = [
        block
        for block in paragraphs(runbook())
        if re.search(r"redeploy", block, re.IGNORECASE) and "Build" in block and re.search(r"merge", block)
    ]
    assert matching, "no step confirms that a later merge to main redeploys staging"


def test_runbook_sets_the_staging_url_for_the_automatic_check():
    # staging-check.yml reads the URL from this repository variable and fails
    # every run until the owner sets it.
    matching = [
        block
        for block in paragraphs(runbook())
        if "STAGING_URL" in block and "staging-check" in block and "https://<staging-app>.streamlit.app" in block
    ]
    assert matching, "the runbook doesn't say to set STAGING_URL for the staging-check workflow"


def test_runbook_uses_placeholders_only():
    text = runbook()
    emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    assert set(emails) <= {"your-email@example.com"}, emails
    assert ".apps.googleusercontent.com" not in text
    assert not re.search(r"https://(?!<)[\w-]+\.streamlit\.app", text), "a real app URL is in the runbook"


# ------------------------------------------------- staging monitor (unit U1)
def monitor_section():
    """The runbook's staging-monitor section, up to the next `## ` heading."""
    text = runbook()
    start = section_start(text, "[Mm]onitor")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def monitor_paragraphs():
    """The section's paragraphs with line breaks folded, so wrapping never matters."""
    return [re.sub(r"\s+", " ", block) for block in paragraphs(monitor_section())]


def test_monitor_section_names_the_workflow_and_both_issue_labels():
    section = re.sub(r"\s+", " ", monitor_section())
    assert "`staging-monitor`" in section
    assert "`staging-outage`" in section
    assert "`staging-outage-practice`" in section


def test_monitor_section_says_what_to_do_when_an_outage_issue_opens():
    matching = [
        block
        for block in monitor_paragraphs()
        if re.search(r"Streamlit'?s? (own )?status", block)
        and re.search(r"[Rr]eboot", block)
        and re.search(r"[Rr]evert", block)
    ]
    assert matching, "no paragraph covers checking Streamlit's status, rebooting the app and reverting"


def test_monitor_section_states_the_detection_delay_and_that_short_outages_may_not_alert():
    section = re.sub(r"\s+", " ", monitor_section())
    assert re.search(r"30 (to|-|and) 60 minutes", section)
    assert re.search(r"best-effort", section)
    assert re.search(r"shorter outage[^.]*(may|might) (never|not) alert", section)


def test_monitor_section_says_asleep_is_not_down_and_a_broken_app_answering_ok_is_not_seen():
    section = re.sub(r"\s+", " ", monitor_section())
    assert re.search(r"[Aa]sleep is not down|sleeping app is not down", section)
    assert re.search(r"answers `ok`[^.]*not (seen|noticed|detected)", section)


def test_monitor_section_explains_how_to_learn_the_real_sleep_answer():
    matching = [
        block
        for block in monitor_paragraphs()
        if "`redirect`" in block and "`unexpected-page`" in block and "`check-detail:`" in block
    ]
    assert matching, "no paragraph explains the sleep-learning step and the check-detail line"


def test_monitor_section_says_how_to_stop_the_monitor_and_that_it_is_temporary():
    matching = [
        block for block in monitor_paragraphs() if "Disable workflow" in block and re.search(r"temporar", block)
    ]
    assert matching, "no paragraph says how to disable the monitor, and that it is temporary"


def test_monitor_section_gives_the_practice_alert_steps_and_pass_criterion():
    section = re.sub(r"\s+", " ", monitor_section())
    assert "practice_address" in section
    assert re.search(r"https://[\w-]+\.invalid", section)
    assert re.search(r"two manual runs?[^.]*at least 5 minutes apart", section)
    assert re.search(r"[Cc]lose the (practice )?issue", section)
    matching = [block for block in monitor_paragraphs() if "notification" in block and "email" in block]
    assert matching, "the drill's pass criterion (issue notification and failed-run email) is missing"


def test_monitor_section_covers_the_60_day_schedule_shutdown():
    matching = [
        block
        for block in monitor_paragraphs()
        if "60 days" in block and re.search(r"Enable workflow|re-?enable", block)
    ]
    assert matching, "no paragraph says GitHub switches the schedule off after 60 days and how to switch it on"


def test_monitor_section_gives_the_bulk_cache_clear_command():
    section = re.sub(r"\s+", " ", monitor_section())
    assert "gh cache list --key staging-monitor-state-" in section
    assert "gh cache delete" in section


MONITOR_WORKFLOW = ROOT / ".github" / "workflows" / "staging-monitor.yml"


def test_monitor_section_stays_in_step_with_the_workflow_and_the_script():
    # Read the values from the code, so renaming one there fails here instead
    # of leaving the runbook stale (a drifted cache prefix would make the
    # clear command silently delete nothing).
    sm = load("staging_monitor")
    workflow = MONITOR_WORKFLOW.read_text()
    section = re.sub(r"\s+", " ", monitor_section())

    cron = re.search(r'cron: "(\d+),(\d+) \* \* \* \*"', workflow)
    assert cron, "the monitor workflow's schedule is not the expected two-minutes-past form"
    assert f"minutes {cron.group(1)} and {cron.group(2)}" in section

    prefix = re.search(r"restore-keys: (\S+)", workflow)
    assert prefix, "the monitor workflow has no restore-keys prefix"
    assert f"gh cache list --key {prefix.group(1)} " in section

    assert f"`{sm.REAL_LABEL}`" in section
    assert f"`{sm.PRACTICE_LABEL}`" in section
    assert "`SLEEP_WORDING`" in section
    assert isinstance(sm.SLEEP_WORDING, tuple) and sm.SLEEP_WORDING


def test_monitor_section_says_a_run_that_stops_early_is_misconfigured():
    # A missing or invalid STAGING_URL ends the run before any check: there is
    # no check:/decision: line, only the script's own usage error.
    matching = [
        block for block in monitor_paragraphs() if "staging_monitor.py: error:" in block and "STAGING_URL" in block
    ]
    assert matching, "the runbook doesn't say what a run that stops on a usage error means"


def test_monitor_section_numbers_and_log_lines_come_from_the_code(tmp_path, capsys):
    # The exit code, the confirm window, the alert delay, the down reasons and
    # the log prefixes are read from the script, so changing one there fails
    # here instead of leaving the runbook stale.
    sm = load("staging_monitor")
    workflow = MONITOR_WORKFLOW.read_text()
    section = re.sub(r"\s+", " ", monitor_section())

    assert f"exits with code {sm.EXIT_USAGE}" in section
    confirm = int(sm.CONFIRM_AFTER.total_seconds() // 60)
    assert f"at least {confirm} minutes apart" in section

    first, second = (int(m) for m in re.search(r'cron: "(\d+),(\d+) ', workflow).groups())
    gap = second - first
    assert gap == 60 - gap, "the schedule is no longer evenly spaced; reword the alert delay"
    assert f"about {gap} to {2 * gap} minutes" in section

    for reason in sm.REASONS:
        if reason not in ("ok", "asleep"):
            assert f"`{reason}`" in section, f"the runbook doesn't list the down reason {reason}"

    assert sm.main(["--state", str(tmp_path / "state.json")], env={}) == sm.EXIT_USAGE
    prefix = capsys.readouterr().err.splitlines()[-1].split(" error:")[0] + " error:"
    assert f"`{prefix}`" in section
    assert 'print(f"check-detail:' in (ROOT / "scripts" / "staging_monitor.py").read_text()


def test_monitor_section_bounds_the_practice_drill_by_the_stale_rule():
    # A second practice run more than STALE_AFTER after the first forgets the
    # first sighting and stays green, which would look like a broken drill.
    sm = load("staging_monitor")
    stale = int(sm.STALE_AFTER.total_seconds() // 60)
    section = re.sub(r"\s+", " ", monitor_section())
    assert f"less than {stale} minutes" in section
    assert any(f"{stale} minutes" in block and "skipped" in block for block in monitor_paragraphs()), (
        "the runbook doesn't say that skipped runs longer than the stale limit reset a half-seen outage"
    )


def test_monitor_section_covers_a_sleep_answer_the_wording_cannot_match_and_a_cancelled_practice_run():
    section = re.sub(r"\s+", " ", monitor_section())
    assert "`SLEEP_WORDING` (or the classifier)" in section
    assert "cancelled" in section and "start it again" in section
