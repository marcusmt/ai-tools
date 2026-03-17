#!/usr/bin/env bash

# Ensures we are in the correct directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Check if a question was provided
if [ -z "$1" ]; then
    echo "Usage: ./ask_router.sh \"Your question here\""
    exit 1
fi

# Run the smart router using the virtual environment's Python
./.venv/bin/python smart_router.py "$1"
