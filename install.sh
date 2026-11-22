#!/bin/sh
set -eu
studio_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Darwin ]; then
    echo 'This installer is for macOS.' >&2
    exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
    for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$brew_bin" ]; then
            eval "$("$brew_bin" shellenv)"
            break
        fi
    done
fi
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    command -v brew >/dev/null 2>&1 || { echo 'Install Homebrew from https://brew.sh first.' >&2; exit 1; }
    brew install python
fi
exec python3 "$studio_dir/setup_dependencies.py" "$@"
