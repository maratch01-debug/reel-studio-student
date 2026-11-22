#!/bin/sh
set -eu
studio_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$studio_dir/studio.py" "$@"
