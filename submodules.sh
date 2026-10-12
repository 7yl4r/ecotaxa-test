#!/usr/bin/env bash
# Initialize the services/ submodules (forks of the upstream ecotaxa repos) and
# configure each for upstream PRs. Idempotent and non-destructive: submodules
# that are already checked out are left on whatever branch/commit they are on;
# only missing ones are cloned, and missing `upstream` remotes are added.
set -euo pipefail
cd "$(dirname "$0")"

for path in $(git config -f .gitmodules --get-regexp '\.path$' | awk '{print $2}'); do
  name=$(basename "$path")
  branch=$(git config -f .gitmodules --get "submodule.$path.branch" || true)

  if [ ! -e "$path/.git" ]; then
    echo "==> Initializing submodule $path..."
    git submodule update --init -- "$path"
    # Land on the working branch instead of a detached HEAD when it matches
    # the pinned commit, so commits made there can be pushed straight away.
    if [ -n "$branch" ] \
       && [ "$(git -C "$path" rev-parse HEAD)" = "$(git -C "$path" rev-parse -q --verify "origin/$branch" || true)" ]; then
      git -C "$path" switch -q "$branch"
    fi
  fi

  if ! git -C "$path" remote get-url upstream >/dev/null 2>&1; then
    git -C "$path" remote add upstream "https://github.com/ecotaxa/$name.git"
    git -C "$path" fetch -q upstream
  fi
done
