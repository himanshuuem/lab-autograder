#!/usr/bin/env bash
# Run every unit-test suite. Used by `make test` and Jenkins.
set -u
cd "$(dirname "$0")/.."
export ALLOW_UNSAFE_LOCAL_BACKEND=1
fail=0
run() {
  local dir=$1; shift
  echo "=================== $dir"
  (cd "$dir" && python -m pytest -q -p no:cacheprovider "$@") || fail=1
}
run packages/docextract tests
run sandbox -m "not docker" tests
run mcp_server tests
run app tests
if [ $fail -ne 0 ]; then echo "SOME TESTS FAILED"; exit 1; fi
echo "ALL TESTS PASSED"
