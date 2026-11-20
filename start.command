#!/bin/zsh
set -e
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'First run: setting up the local audio environment.'
  ./setup.command
fi
exec .venv/bin/python launch.py
