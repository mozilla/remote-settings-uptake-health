# remote-settings-health

The objective of this script is to check in on the collected uptake from Telemetry
with respect to Remote Settings. Essentially, across all statuses that we worry
about, we use this script to check that the amount of bad statuses don't exceed
a threshold.

The ultimately use case for this script is to run it periodically and use it to
trigger alerts/notifications that the Product Delivery team can take heed of.

## Architectural Overview

### In Plain English

This is stateless script, written in Python, meant to be executed roughly once a day.
It queries [Redash](https://sql.telemetry.mozilla.org) for
a Redash query's data that is pre-emptively run every 24 hours.
The data it analyses is a
list of everything stored in "Remote Content" along with a count of
every possible status (e.g. `up_to_date`, `network_error`, etc.)
The script sums the "good" statuses and compares it against the "bad" statuses and
if that ratio (expressed as a percentage) is over a certain threshold it alerts
by sending an event to Sentry which notifies the team by email.

### Historical Strategy

As of Firefox Nightly 67, Firefox clients that use Remote Settings only
send Telemetry pings in daily batches.
I.e. it's _not_ real-time. The "uptake histogram" is buffered in
the browser and will send periodically instead of as soon as possible. In Firefox
Nightly (67 at the time of writing),
[we are switching to real-time Telemetry Events](https://bugzilla.mozilla.org/show_bug.cgi?id=1517469).

On the Telemetry backend we're still consuming the older uptake histogram but once,
the population using the new Telemetry Events is large enough,
we will switch the Redash query (where appropriate) and still use
this script to worry about the percentage thresholds.
And the strategy for notifications should hopefully not change. There is no plan
to rush this change since we'll still be doing "legacy" histogram telemetry
_and_ the new telemetry events so we can let it mature a bit before changing
the source of data.

Although we will eventually switch to real-time Telemetry Events, nothing changes in
terms of the surface API but the underlying data is more up-to-date and the response
time of reacting to failure spikes is faster.

It is worth noting that as underlying tools change, we might decommission this
solution and use something native to the Telemetry analysis tools that achives
the same goal.

### Redash

The query we use is mentioned as a config default in the main `main.py` file.
Follow that link, without the API key, in your browser to study the query and/or
to fork it for a better query when applicable.

### Configuration

This script encodes all configuration inside `main.py` as defaults for things
that can be overwritten by environment variables.

The only **mandatory environment variable** is `REDASH_API_KEY`. You get this
by logging in [https://sql.telemetry.mozilla.org](https://sql.telemetry.mozilla.org)
and click to edit the/any relevant query and in the upper right-hand corner there's a
drop-down with the label "..." and inside it "Show API Key".

Either put this into a `.env` file or use it as a regular sourced enviroment variable.
E.g.:

```bash
    $ cat .env
    REDASH_API_KEY=MXAqPP1Q4FNLjHeT1w
```

For most other configuration options, the best strategy is to study all the
uppercased constants in the `main.py` file.

## To hack on

```bash
$ pip install -e ".[dev,test]"
$ REDASH_API_KEY=OCZccH...FhB4cT python main.py
```

The only mandatory environment variable is `REDASH_API_KEY`. All other variables
are encoded as good defaults inside `main.py` and can all be overwritten with
environment variables.

To not have to put the `REDASH_API_KEY` on the command line every time you can either
run:

```bash
export REDASH_API_KEY=OCZccH...FhB4cT
```

or, create a `.env` file that looks like this:

```bash
$ cat .env
REDASH_API_KEY=OCZccH...FhB4cT
```

Another useful variable is `DEBUG=true`. If you use this, all repeated network
requests are cached to disk. Note! If you want to invalidate that cache, delete
the file `requests_cache1.sqlite`.

## Running tests

The simplest form is to run:

```bash
$ pip install -e ".[dev,test]"
```

...if you haven't already done so. Then run:

```bash
$ pytest
```

You can also invoke it with:

```bash
$ ./run.sh test
```

## Docker

To build:

    docker build -t remote-settings-uptake-health .

To run:

    docker run -t --env-file .env remote-settings-uptake-health

Note, this is the same as running:

    docker run -t --env-file .env remote-settings-uptake-health main

Or, to see what other options are available:

    docker run -t --env-file .env remote-settings-uptake-health main --help

To run the unit tests with docker use:

    docker run -t remote-settings-uptake-health test

To run the linting checks with docker use:

    docker run -t remote-settings-uptake-health lintcheck

And if you just want to fix any lint warnings (that can be automated):

    docker run -t remote-settings-uptake-health lintfix

To get into a `bash` prompt inside the docker container run:

    docker run -it --env-file .env remote-settings-uptake-health bash
    python main.py  # for example

## Code style

We enforce all Python code style with `black` and `flake8`. The best tool to test this is with `therapist` which is installed as a dev package. To run it;

    therapist run

That will check all the files you've touched in the current branch.
To test across _all_ files, including those you haven't touched:

    therapist use lint:all

If you do get warnings from this, you can either fix it manually
in your editor or run:

    therapist use fix

Even better, if you intend to work on this repo a lot, install `therapist` as a pre-commit git hook:

    therapist install

Now, trying to commit, with code style warnings, will prevent you and
you have to run the above (`therapist use fix`) fix command.
