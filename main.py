from fnmatch import fnmatch
from urllib.parse import urlencode

import click
import requests
import toml
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

DEFAULT_EXCLUDE_SOURCES = config(
    "EXCLUDE_SOURCES",
    cast=Csv(),
    default="shield-recipe-client/*, normandy/*, main/url-classifier-skip-urls",
)

# XXX What about instead just say that `bad == status.endswith('_error')`??
DEFAULT_GOOD_STATUSES = config(
    "GOOD_STATUSES", cast=Csv(), default="success, up_to_date"
)

# XXX What about 'backoff' ??
DEFAULT_NEUTRAL_STATUSES = config(
    "NEUTRAL_STATUSES", cast=Csv(), default="pref_disabled"
)

# Statuses to ignore if their total good+bad numbers are less than this.
DEFAULT_MIN_TOTAL_ENTRIES = config("MIN_TOTAL_ENTRIES", cast=int, default=0)

DEFAULT_ERROR_THRESHOLD_PERCENT = config(
    "DEFAULT_ERROR_THRESHOLD_PERCENT", cast=float, default=2.0
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


def run_config_file(conf, verbose=False, dry_run=False):
    def log(*args):
        if verbose:
            click.echo(" ".join(str(x) for x in args))

    exclude_patterns = conf.get("exclude_sources", DEFAULT_EXCLUDE_SOURCES)

    def exclude_source(source):
        return any(fnmatch(source, pattern) for pattern in exclude_patterns)

    good_statuses = conf.get("good_statuses", DEFAULT_GOOD_STATUSES)

    def is_good(status):
        return status in good_statuses

    neutral_statuses = conf.get("neutral_statuses", DEFAULT_NEUTRAL_STATUSES)

    def is_neutral(status):
        return status in neutral_statuses

    min_total_entries = conf.get("min_total_entries", DEFAULT_MIN_TOTAL_ENTRIES)
    default_error_threshold_percent = conf.get(
        "error_threshold_percent", DEFAULT_ERROR_THRESHOLD_PERCENT
    )

    downloader = Downloader(timeout_seconds=conf.get("timeout_seconds", 60))
    data = downloader.download()

    query_result = data["query_result"]
    data = query_result["data"]
    rows = data["rows"]
    count_bad = 0
    for row in rows:
        source = row.pop("source")

        if exclude_source(source):
            log(f"Skipping {source!r} because it's excluded")
            continue

        source_conf = conf.get(source, {})
        error_threshold_percent = source_conf.get(
            "error_threshold_percent", default_error_threshold_percent
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

        if good + bad < min_total_entries:
            log(
                f"Skipping {source!r} because exactly too few good+bad statuses "
                f"({good + bad} < {min_total_entries})"
            )
            continue

        percent = 100 * bad / (good + bad)
        stats = f"(good:{good:,} bad:{bad:,})"
        is_bad = percent > error_threshold_percent
        click.secho(
            f"{source:40} {stats:40} {percent:>10.2f}%", fg="red" if is_bad else None
        )
        if is_bad:
            count_bad += 1
    return count_bad


def error_out(msg, raise_abort=True):
    click.echo(click.style(msg, fg="red"))
    if raise_abort:
        raise click.Abort


@click.command()
@click.option("-v", "--verbose", is_flag=True)
@click.option("-d", "--dry-run", is_flag=True)
@click.argument("configfile", type=click.File("r"))
def cli(configfile, dry_run, verbose):
    config = toml.load(configfile)
    bads = run_config_file(config, verbose=verbose, dry_run=dry_run)
    if bads:
        error_out(f"{bads} settings have a bad ratio over threshold.")


if __name__ == "__main__":
    cli()
