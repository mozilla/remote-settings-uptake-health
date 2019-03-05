import responses

from main import run, Downloader, REDASH_API_QUERY_URL, REDASH_API_KEY


@responses.activate
def test_downloader():
    assert "example.com" in REDASH_API_QUERY_URL, REDASH_API_QUERY_URL
    expected_url = f"{REDASH_API_QUERY_URL}?api_key={REDASH_API_KEY}"
    responses.add(responses.GET, expected_url, json={"foo": "bar"})
    d = Downloader()
    json_response = d.download()
    assert json_response == {"foo": "bar"}


@responses.activate
def test_run_no_problems(capsys):
    expected_url = f"{REDASH_API_QUERY_URL}?api_key={REDASH_API_KEY}"
    redash_data = {
        "query_result": {
            "data": {
                "rows": [
                    {
                        "source": "foo/bar",
                        "min_timestamp": 1_551_657_600,
                        "max_timestamp": 1_551_743_999,
                        "success": 123_456,
                        "up_to_date": 234_567,
                        "network_error": 1234,
                        "sync_error": 123,
                        "pref_disabled": 1_000_000,
                    },
                    # This one should be ignored
                    {
                        "source": "trouble/maker",
                        "min_timestamp": 1_551_657_600,
                        "max_timestamp": 1_551_743_999,
                        "success": 100_000,
                        "up_to_date": 200_000,
                        "network_error": 75000,
                        "sync_error": 5000,
                    },
                ]
            }
        }
    }
    responses.add(responses.GET, expected_url, json=redash_data)

    bad_rows = run()
    assert not bad_rows, bad_rows

    good = 123_456 + 234_567
    bad = 1234 + 123
    error_rate = 100 * bad / (good + bad)
    error_rate_str = f"{error_rate:.2f}%"
    captured = capsys.readouterr()
    assert error_rate_str in captured.out
    assert "From 2019-03-04 00:00:00 to 2019-03-04 23:59:59" in captured.out


@responses.activate
def test_run_problems(capsys):
    expected_url = f"{REDASH_API_QUERY_URL}?api_key={REDASH_API_KEY}"
    redash_data = {
        "query_result": {
            "data": {
                "rows": [
                    {
                        "source": "foo/bar",
                        "min_timestamp": 1_551_657_600,
                        "max_timestamp": 1_551_743_999,
                        "success": 123_456,
                        "up_to_date": 234_567,
                        "network_error": 12340,
                        "sync_error": 123,
                        "pref_disabled": 1_000_000,  # remember, neutral and ignored
                    }
                ]
            }
        }
    }
    responses.add(responses.GET, expected_url, json=redash_data)

    bad_rows = run()
    assert bad_rows
    bad_row, = bad_rows
    assert bad_row[0] == "foo/bar"
    assert bad_row[1] == 123_456 + 234_567 + 12340 + 123
    bad_keys = [x[0] for x in bad_row[2]]
    assert bad_keys == ["network_error", "sync_error"]

    captured = capsys.readouterr()
    # This will result in a error rate of 3.36%
    # which is more than the DEFAULT_ERROR_THRESHOLD_PERCENT
    # set in pytest.ini.
    good = 123_456 + 234_567
    bad = 12340 + 123
    error_rate = 100 * bad / (good + bad)
    error_rate_str = f"{error_rate:.2f}%"
    assert error_rate_str in captured.out
    assert "foo/bar" in captured.out
    assert f"{good:,}" in captured.out
    assert f"{bad:,}" in captured.out
