#!/usr/bin/env bash
set -eo pipefail

usage() {
  echo "usage: ./run.sh main|test"
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
  *)
    exec "$@"
    ;;
esac
