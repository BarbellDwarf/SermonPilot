import time
from sermon_updater import (
    SERMON_FILTER_ARG_MAP,
    cli_main,
    SermonLite,
)

# We'll monkeypatch fetch_sermons to capture params passed from cli_main.

captured_params = {}

def dummy_fetch_sermons(params, max_results=None):  # signature match
    global captured_params
    captured_params = dict(params)
    # Return a single dummy sermon so --list-only path prints something then exits
    return [SermonLite(sermonID="TEST1234567890", displayTitle="Test Sermon", preachDate="2024-01-01", speakerName="Tester", eventType="Event")]  # noqa: E501


def build_all_filter_args():
    args = []
    now = int(time.time())
    sample_values = {
        'page': '2',
        'page_size': '10',
        'chapter': '1',
        'chapter_end': '2',
        'verse': '3',
        'verse_end': '4',
        'preached_year': '2024',
        'month': '5',
        'day': '6',
        'audio_min_duration': '60',
        'audio_max_duration': '600',
        'speaker_id': '123',
        'collection_id': '456',
        'preached_after': str(now - 86400),
        'preached_before': str(now),
        'sermon_ids': '1000000000000,1000000000001',
    }
    for cli_name, (_api, kind, _help) in SERMON_FILTER_ARG_MAP.items():
        flag = f"--{cli_name.replace('_','-')}"
        if kind in ('flag', 'negflag'):
            args.append(flag)
        else:
            value = sample_values.get(cli_name, 'sample')
            args.extend([flag, value])
    # ensure we don't trigger processing; just listing
    args.append('--list-only')
    args.append('--auto-yes')
    return args


def test_cli_all_filters_monkeypatched(monkeypatch, capsys):
    # Patch fetch_sermons inside sermon_updater module
    monkeypatch.setattr('sermon_updater.fetch_sermons', dummy_fetch_sermons)
    all_args = build_all_filter_args()
    cli_main(all_args)
    # Flush output just in case
    capsys.readouterr()

    # Verify each filter flag resulted in expected API param
    for cli_name, (api_name, kind, _help) in SERMON_FILTER_ARG_MAP.items():
        if kind == 'flag':
            assert captured_params.get(api_name) == 'true', f"Flag {cli_name} -> {api_name} missing/incorrect"  # noqa: E501
        elif kind == 'negflag':
            assert captured_params.get(api_name) == 'false', f"NegFlag {cli_name} -> {api_name} missing/incorrect"  # noqa: E501
        else:
            # Provided value should appear directly (converted to int where parser applies)
            assert api_name in captured_params, f"Param for {cli_name} ({api_name}) not found"

    # Special: broadcasterID should still be injected by cli_main even if not supplied
    assert 'broadcasterID' in captured_params
