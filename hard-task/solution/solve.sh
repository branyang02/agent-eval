#!/bin/bash
set -e

# Use this file to solve the task.

cd "$(dirname "$0")"

g++ -O2 -std=c++17 compute_primes.cpp -o /tmp/compute_primes
/tmp/compute_primes

python3 summarize.py
