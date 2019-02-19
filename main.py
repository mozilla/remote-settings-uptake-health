from fnmatch import fnmatch
from urllib.parse import urlencode

import click
import requests
from decouple import config, undefined, Csv
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry

DEBUG = config("DEBUG", default=False)
if DEBUG:
    # Temporary for hacking. Just prevents the same URL to be downloaded twice.
    import requests_cache

    requests_cache.install_cache(
        "requests_cache1", expire_after=60 * 5, allowable_methods=["GET", "PUT"]
    )
    print(
        "Warning! Running in debug mode means all HTTP requests are cached "
        "indefinitely. To reset HTTP caches, delete the file 'requests_cache1.sqlite'"
    )


REDASH_API_QUERY_URL = config(
    "REDASH_API_QUERY_URL",
    default="https://sql.telemetry.mozilla.org/api/queries/61352/results.json",
)
REDASH_API_KEY = config(
    "REDASH_API_KEY",
    default=undefined if "api_key=" not in REDASH_API_QUERY_URL else None,
)

REDASH_TIMEOUT_SECONDS = config("REDASH_TIMEOUT_SECONDS", cast=int, default=60)

EXCLUDE_SOURCES = config(
    "EXCLUDE_SOURCES",
    cast=Csv(),
    default="shield-recipe-client/*, normandy/*, main/url-classifier-skip-urls",
)

# XXX What about instead just say that `bad == status.endswith('_error')`??
GOOD_STATUSES = config("GOOD_STATUSES", cast=Csv(), default="success, up_to_date")

# XXX What about 'backoff' ??
NEUTRAL_STATUSES = config("NEUTRAL_STATUSES", cast=Csv(), default="pref_disabled")

# Statuses to ignore if their total good+bad numbers are less than this.
MIN_TOTAL_ENTRIES = config("MIN_TOTAL_ENTRIES", cast=int, default=1000)

DEFAULT_ERROR_THRESHOLD_PERCENT = config(
    "DEFAULT_ERROR_THRESHOLD_PERCENT", cast=float, default=2.0
)


def _parse_threshold_percent(s):
    name, percentage = s.split("=")
    return (name.strip(), float(percentage))


SPECIFIC_ERROR_THRESHOLD_PERCENT = dict(
    config(
        "SPECIFIC_ERROR_THRESHOLD_PERCENT",
        cast=Csv(cast=_parse_threshold_percent, delimiter=";"),
        default=("main/collection = 10; foo/bar = 2 "),
    )
)


session = requests.Session()


def requests_retry_session(
    retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)
):
    """Opinionated wrapper that creates a requests session with a
    HTTPAdapter that sets up a Retry policy that includes connection
    retries.

    If you do the more naive retry by simply setting a number. E.g.::

        adapter = HTTPAdapter(max_retries=3)

    then it will raise immediately on any connection errors.
    Retrying on connection errors guards better on unpredictable networks.
    From http://docs.python-requests.org/en/master/api/?highlight=retries#requests.adapters.HTTPAdapter
    it says: "By default, Requests does not retry failed connections."

    The backoff_factor is documented here:
    https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#urllib3.util.retry.Retry
    A default of retries=3 and backoff_factor=0.3 means it will sleep like::

        [0.3, 0.6, 1.2]
    """  # noqa
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class Downloader:
    def __init__(self, timeout_seconds=10):
        self.timeout = timeout_seconds
        self.session = requests_retry_session(
            backoff_factor=10, status_forcelist=(503, 504)
        )

    def download(self, url=None, params=None):
        if url is None:
            url = REDASH_API_QUERY_URL
            if "api_key=" not in url:
                params = params or {}
                params["api_key"] = REDASH_API_KEY
        if params:
            url += "&" if "?" in url else "?"
            url += urlencode(params)
        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except HTTPError:
            print(response.text)
            raise
        return response.json()


def run(verbose=False, dry_run=False):
    def log(*args):
        if verbose:
            click.echo(" ".join(str(x) for x in args))

    def exclude_source(source):
        return any(fnmatch(source, pattern) for pattern in EXCLUDE_SOURCES)

    def is_good(status):
        return status in GOOD_STATUSES

    def is_neutral(status):
        return status in NEUTRAL_STATUSES

    downloader = Downloader(timeout_seconds=REDASH_TIMEOUT_SECONDS)
    data = downloader.download()

    query_result = data["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    bad_rows = []
    for row in rows:
        source = row.pop("source")

        if exclude_source(source):
            log(f"Skipping {source!r} because it's excluded")
            continue

        error_threshold_percent = SPECIFIC_ERROR_THRESHOLD_PERCENT.get(
            source, DEFAULT_ERROR_THRESHOLD_PERCENT
        )

        good = bad = 0
        for status, count in row.items():
            log(
                status.ljust(20),
                f"{count:,}".rjust(10),
                (is_good(status) and "good")
                or (not is_neutral(status) and "bad")
                or "neutral",
            )
            if is_good(status):
                good += row[status]
            elif not is_neutral(status):
                bad += row[status]
        if not (good + bad):
            log(f"Skipping {source!r} because exactly 0 good+bad statuses")
            continue

        if good + bad < MIN_TOTAL_ENTRIES:
            log(
                f"Skipping {source!r} because exactly too few good+bad statuses "
                f"({good + bad} < {MIN_TOTAL_ENTRIES})"
            )
            continue

        percent = 100 * bad / (good + bad)
        stats = f"(good:{good:>10,} bad:{bad:>10,})"
        is_bad = percent > error_threshold_percent
        click.secho(
            f"{source:40} {stats:40} {percent:>10.2f}%", fg="red" if is_bad else None
        )
        if is_bad:
            bad_statuses = [
                (s, v)
                for s, v in row.items()
                if s not in GOOD_STATUSES + NEUTRAL_STATUSES
            ]
            bad_rows.append((source, bad_statuses))

    return bad_rows


@click.command()
@click.option("-v", "--verbose", is_flag=True)
@click.option("-d", "--dry-run", is_flag=True)
def cli(dry_run, verbose):
    bads = run(verbose=verbose, dry_run=dry_run)
    if bads:
        click.secho(
            f"\n{len(bads)} settings have a bad ratio over threshold.", fg="red"
        )
        for source, statuses in bads:
            statuses_desc = sorted(statuses, key=lambda e: e[1], reverse=True)
            stats = " ".join([f"{s}:{v:,}" for s, v in statuses_desc if v > 0])
            click.secho(f"{source:40} ({stats})")

        raise click.Abort


if __name__ == "__main__":
    cli()
