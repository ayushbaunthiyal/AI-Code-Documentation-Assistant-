# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (git is needed for GitPython)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY pyproject.toml .

# Install dependencies
RUN uv sync --no-install-project

# Copy the rest of the application code
COPY . .

# Make sure the environment is available
ENV PATH="/app/.venv/bin:$PATH"
