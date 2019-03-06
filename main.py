from datetime import datetime
from fnmatch import fnmatch
from urllib.parse import urlencode

import click
import requests
import sentry_sdk
from decouple import config, undefined, Csv
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError
from requests.packages.urllib3.util.retry import Retry


DEBUG = config("DEBUG", cast=bool, default=False)
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
assert "api_key=" not in REDASH_API_QUERY_URL, "set in REDASH_API_KEY instead"

REDASH_API_KEY = config(
    "REDASH_API_KEY",
    default=undefined if "api_key=" not in REDASH_API_QUERY_URL else None,
)

SENTRY_DSN = config("SENTRY_DSN", default=None)

REDASH_TIMEOUT_SECONDS = config("REDASH_TIMEOUT_SECONDS", cast=int, default=60)

EXCLUDE_SOURCES = config(
    "EXCLUDE_SOURCES",
    cast=Csv(),
    default="shield-recipe-client/*, normandy/*, main/url-classifier-skip-urls",
)

# Statuses to ignore if their total good+bad numbers are less than this.
MIN_TOTAL_ENTRIES = config("MIN_TOTAL_ENTRIES", cast=int, default=1000)

DEFAULT_ERROR_THRESHOLD_PERCENT = config(
    "DEFAULT_ERROR_THRESHOLD_PERCENT", cast=float, default=2.0
)


def _parse_threshold_percent(s):
    name, percentage = s.split("=")
    return (name.strip(), float(percentage))


# To override this, if you want, for a particular key, override the specific
# threshold, the format is like this:
#
#    SPECIFIC_ERROR_THRESHOLD_PERCENTAGES="main/mycollection = 5.5; foo/bar= 12"
#
# That means that the error threshold is 5.5% specifically for 'main/collection' and
# 12.0% for 'foo/bar'.
SPECIFIC_ERROR_THRESHOLD_PERCENTAGES = dict(
    config(
        "SPECIFIC_ERROR_THRESHOLD_PERCENTAGES",
        cast=Csv(cast=_parse_threshold_percent, delimiter=";"),
        default="",
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

    def is_bad(status):
        return status.endswith("_error")

    downloader = Downloader(timeout_seconds=REDASH_TIMEOUT_SECONDS)
    data = downloader.download()

    query_result = data["query_result"]
    data = query_result["data"]
    rows = data["rows"]

    # Determine the date range of this dataset.
    min_timestamp = min(row["min_timestamp"] for row in rows)
    max_timestamp = max(row["max_timestamp"] for row in rows)
    click.secho(
        "📅 From {} to {}".format(
            datetime.utcfromtimestamp(min_timestamp),
            datetime.utcfromtimestamp(max_timestamp),
        )
    )

    bad_rows = []
    for row in rows:
        source = row["source"]
        if exclude_source(source):
            log(f"Skipping {source!r} because it's excluded")
            continue

        error_threshold_percent = SPECIFIC_ERROR_THRESHOLD_PERCENTAGES.get(
            source, DEFAULT_ERROR_THRESHOLD_PERCENT
        )

        good = bad = 0
        bad_statuses = []
        count_per_status = [
            (s, c)
            for s, c in row.items()
            if s not in ("source", "min_timestamp", "max_timestamp")
        ]
        for status, count in count_per_status:
            log(
                status.ljust(20),
                f"{count:,}".rjust(10),
                ("bad" if is_bad(status) else "good"),
            )
            if is_bad(status):
                bad += row[status]
                bad_statuses.append((status, count))
            else:
                good += row[status]
        total = good + bad
        if not total:
            log(f"Skipping {source!r} because exactly 0 good+bad statuses")
            continue

        if total < MIN_TOTAL_ENTRIES:
            log(
                f"Skipping {source!r} because exactly too few good+bad statuses "
                f"({total} < {MIN_TOTAL_ENTRIES})"
            )
            continue

        percent = 100 * bad / total
        stats = f"(good:{good:>10,} bad:{bad:>10,})"
        is_erroring = percent > error_threshold_percent
        click.secho(
            f"{source:40} {stats:40} {percent:>10.2f}%",
            fg="red" if is_erroring else None,
        )
        if is_erroring:
            bad_rows.append((source, total, bad_statuses))

    return bad_rows


@click.command()
@click.option("-v", "--verbose", is_flag=True)
@click.option("-d", "--dry-run", is_flag=True)
def cli(dry_run, verbose):
    if SENTRY_DSN:
        # Note! If you don't do `sentry_sdk.init(DSN)` it will still work
        # to do things like calling `sentry_sdk.capture_exception(exception)`
        # It just means it's a noop.
        sentry_sdk.init(SENTRY_DSN)
    elif not DEBUG:
        click.secho("No SENTRY_DSN set but not in DEBUG mode!", bold=True)

    try:
        bads = run(verbose=verbose, dry_run=dry_run)
    except Exception as exception:
        # We use Sentry for two things: General unexpected Python exceptions
        # and plain message. This capture is for the unexpected exceptions.
        sentry_sdk.capture_exception(exception)
        raise

    with sentry_sdk.configure_scope() as scope:
        # Append any extra useful information.
        scope.set_extra("REDASH_API_QUERY_URL", REDASH_API_QUERY_URL)
        scope.set_extra("EXCLUDE_SOURCES", EXCLUDE_SOURCES)
        scope.set_extra(
            "DEFAULT_ERROR_THRESHOLD_PERCENT", DEFAULT_ERROR_THRESHOLD_PERCENT
        )
        scope.set_extra(
            "SPECIFIC_ERROR_THRESHOLD_PERCENTAGES", SPECIFIC_ERROR_THRESHOLD_PERCENTAGES
        )

        if bads:
            click.secho(
                f"\n{len(bads)} settings have a bad ratio over threshold.", fg="red"
            )
        for source, total, statuses in bads:
            statuses_desc = sorted(statuses, key=lambda e: e[1], reverse=True)
            stats = "\n".join(
                [
                    f"\t{s:<16} {v/total*100:.2f}% ({v:,})"
                    for s, v in statuses_desc
                    if v > 0
                ]
            )
            click.secho(f"\n{source}\n{stats}")

            # Remember, this will noop if the SENTRY_DSN is not already set.
            message = f"{source} is erroring too much.\n"
            message += stats
            sentry_sdk.capture_message(message)


if __name__ == "__main__":
    cli()
