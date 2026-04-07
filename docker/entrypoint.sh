#!/bin/bash
set -e

# PetaLinux is NOT sourced here intentionally.
# Its cross-compiler toolchain pollutes PATH and breaks native pip builds.
# The run script sources PetaLinux AFTER installing Python dependencies.

exec "$@"
