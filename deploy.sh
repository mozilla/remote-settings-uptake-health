#!/usr/bin/env bash
set -eu

# Note! This copied from https://github.com/mozilla/normandy

# Usage: retry MAX CMD...
# Retry CMD up to MAX times. If it fails MAX times, returns failure.
# Example: retry 3 docker push "mozilla/remote-settings-uptake-health:$TAG"
function retry() {
    max=$1
    shift
    count=1
    until "$@"; do
        count=$((count + 1))
        if [[ $count -gt $max ]]; then
            return 1
        fi
        echo "$count / $max"
    done
    return 0
}

# configure docker creds
echo "$DOCKER_PASSWORD" | docker login --username="$DOCKER_USERNAME" --password-stdin

# docker tag and push git branch to dockerhub
if [ -n "$1" ]; then
    # Tag built image
    docker tag "remote-settings-uptake-health:$CIRCLE_SHA1" mozilla/remote-settings-uptake-health:latest
    if [ "$1" == master ]; then
        TAG=latest
    else
        TAG="$1"
        docker tag mozilla/remote-settings-uptake-health:latest "mozilla/remote-settings-uptake-health:$TAG" ||
            (echo "Couldn't re-tag mozilla/remote-settings-uptake-health:latest as mozilla/remote-settings-uptake-health:$TAG" && false)
    fi
    retry 3 docker push "mozilla/remote-settings-uptake-health:$TAG" ||
        (echo "Couldn't push mozilla/remote-settings-uptake-health:$TAG" && false)
    echo "Pushed mozilla/remote-settings-uptake-health:$TAG"
fi
