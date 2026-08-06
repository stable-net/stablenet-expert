"""Per-dependency checks for core-dev's setup script.

setup.py owns the contract surface (--check / --fix / --json, settings writes). Each module
here owns one dependency: how to tell whether it is ready, and what to do when it is not.
Splitting them keeps setup.py's REQUIRED table about *values* while dependencies that are
not env vars -- an external plugin, a binary, a remote endpoint -- get room for the logic
their state actually needs.

Stdlib only, per ADR-0014: doctor runs these on machines that have installed nothing yet.
"""
