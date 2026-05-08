FROM ubuntu:24.04

# Install or copy over any environment dependencies here.

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    python3 \
    && rm -rf /var/lib/apt/lists/*
