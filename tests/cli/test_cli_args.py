from sermon_updater import build_arg_parser, build_sermon_query_params, SERMON_FILTER_ARG_MAP  # noqa: E401


def test_minimal_parser_includes_filters():
    parser = build_arg_parser()
    help_text = parser.format_help()
    # ensure each CLI flag (converted) appears in help
    missing = []
    for cli_name in SERMON_FILTER_ARG_MAP:
        flag = f"--{cli_name.replace('_','-')}"
        if flag not in help_text:
            missing.append(flag)
    assert not missing, f"Missing flags in help: {missing}"


def test_build_params_basic():
    parser = build_arg_parser()
    args = parser.parse_args([
        '--search-keyword','grace',
        '--require-audio',
        '--page-size','25',
        '--since-days','7'
    ])
    params = build_sermon_query_params(args)
    assert params['searchKeyword'] == 'grace'
    assert params['requireAudio'] == 'true'
    assert params['pageSize'] == 25
    assert 'preachedAfterTimestamp' in params
