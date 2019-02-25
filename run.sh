#!/usr/bin/env bash
set -eo pipefail

usage() {
  echo "usage: ./run.sh main|test|lintcheck|lintfix"
  exit 1
}

case $1 in
  main)
    shift
    python main.py "$@"
    ;;
  test)
    shift
    pytest "$@"
    ;;
  lintcheck)
    shift
    # Can't use therapist in docker because the .git directory isn't mounted.
    black --check --diff .
    flake8 .
    ;;
  lintfix)
    shift
    # Can't use therapist in docker because the .git directory isn't mounted.
    black .
    ;;
  *)
    exec "$@"
    ;;
esac
