import os
import re
import pytest

import sermon_updater  # imports config & sets API key


@pytest.mark.network
@pytest.mark.live
def test_cli_live_fetch_returns_results(capsys):
    """Integration test hitting the real SermonAudio API.

    Skips automatically if:
      * Config file (sermon_updater.CONFIG_PATH) not present
      * API key missing / blank
      * Environment variable SA_UPDATER_SKIP_LIVE is set
      * Network/API error occurs (converted to skip to avoid CI hard failure)
    """
    if os.environ.get("SA_UPDATER_SKIP_LIVE"):
        pytest.skip("Live API tests disabled via SA_UPDATER_SKIP_LIVE")
    if not os.path.exists(sermon_updater.CONFIG_PATH):
        pytest.skip("Config file missing for live test")
    if not getattr(sermon_updater, "SERMON_AUDIO_API_KEY", None):
        pytest.skip("API key missing; cannot run live test")

    # Use modest window & small limit for speed
    argv = [
        "--since-days", "30",
        "--limit", "2",
        "--list-only",
        "--auto-yes",
        "--cache",
    ]
    try:
        sermon_updater.cli_main(argv)
    except Exception as e:  # Network / auth errors cause skip
        pytest.skip(f"Live API call failed or unavailable: {e}")

    out = capsys.readouterr().out
    assert "No sermons matched filters" not in out, "Expected at least one sermon from live API"

    # Extract matched count
    m = re.search(r"Matched (\d+) sermons", out)
    assert m, "Did not find 'Matched N sermons' line in output"
    count = int(m.group(1))
    assert count > 0, "Matched count was zero"

    # Ensure at least one listed sermon line with expected pipe-separated columns
    sermon_lines = [ln for ln in out.splitlines() if re.search(r"\d{4}-\d{2}-\d{2} .*\|.*\|", ln)]
    assert sermon_lines, "Did not find any sermon listing lines"
