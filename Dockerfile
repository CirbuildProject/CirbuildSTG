# Use a standard Ubuntu base image
FROM ubuntu:22.04

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies required to build Google XLS
RUN apt-get update && apt-get install -y \
    build-essential \
    clang \
    git \
    python3 \
    python3-pip \
    curl \
    zip \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Bazelisk (the Bazel wrapper recommended by Google)
RUN curl -L https://github.com/bazelbuild/bazelisk/releases/download/v1.19.0/bazelisk-linux-amd64 -o /usr/local/bin/bazel \
    && chmod +x /usr/local/bin/bazel

# Create the xls-developer user to match your pipeline's exact expected paths
RUN useradd -m -s /bin/bash xls-developer
USER xls-developer
WORKDIR /home/xls-developer

# Clone the Google XLS repository
RUN git clone https://github.com/google/xls.git

# Build the specific tools CirbuildSTG uses (xlscc, opt_main, codegen_main)
WORKDIR /home/xls-developer/xls
RUN bazel build -c opt //xls/contrib/xlscc:xlscc
RUN bazel build -c opt //xls/tools:opt_main
RUN bazel build -c opt //xls/tools:codegen_main

# Set the working directory for when the container runs
WORKDIR /workspace