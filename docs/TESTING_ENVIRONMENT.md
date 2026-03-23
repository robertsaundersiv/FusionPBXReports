# Testing Environment and Proxmox Runtime Parity

This project now supports two testing modes:

1. Fast local unit tests using your active Python environment.
2. Linux container tests using docker-compose to mirror production runtime assumptions.

## Local Backend Tests (fast feedback)

From project root:

- Windows PowerShell:
  - .\\.venv\\Scripts\\Activate.ps1
  - pytest backend/tests -q

- Linux/macOS:
  - source .venv/bin/activate
  - pytest backend/tests -q

## Production-Like Tests (Linux containers)

Run backend tests with Postgres and Redis in containers:

- docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend-tests

Clean up containers and volumes after test run:

- docker compose -f docker-compose.test.yml down -v

Why this helps:
- Uses Debian-based Python container, matching production Linux behavior more closely than native Windows.
- Validates package installation and runtime startup assumptions in the same image family used for deployment.
- Ensures service dependencies (Postgres, Redis) are available in CI-like conditions.

## Optional Proxmox Host Detail Collection (SSH)

If you want full environment parity with your Proxmox host, collect and compare these runtime details:

- ssh <user>@<proxmox-host>
- uname -a
- cat /etc/os-release
- docker --version
- docker compose version
- python3 --version
- free -h
- nproc
- df -h

Use the collected values to validate:
- Base OS version compatibility.
- Docker and compose feature compatibility.
- Python major/minor version parity.
- Resource limits (memory/cpu/disk) for test workloads.

## Recommended Workflow

1. Run local unit tests while coding.
2. Run containerized tests before each push or deployment.
3. If failures happen only in production, collect host details via SSH and compare against local container assumptions.
