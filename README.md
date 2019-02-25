# remote-settings-health

The objective of this script is to check in on the collected uptake from Telemetry
with respect to Remote Settings. Essentially, across all statuses that we worry
about, we use this script to check that the amount of bad statuses don't exceed
a threshold.

The ultimately use case for this script is to run it periodically and use it to
trigger alerts/notifications that the Product Delivery team can take heed of.

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
