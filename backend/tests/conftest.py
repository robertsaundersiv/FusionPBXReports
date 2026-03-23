"""Shared pytest bootstrapping for deterministic local and container test runs."""

import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
	sys.path.insert(0, str(BACKEND_ROOT))


# Defaults that let unit tests import app modules without relying on local .env.
os.environ.setdefault("DB_USER", "phonereports_user")
os.environ.setdefault("DB_PASSWORD", "phonereports_pass")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_NAME", "phonereports")
os.environ.setdefault("DB_VALIDATE_ON_STARTUP", "false")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FUSIONPBX_HOST", "http://localhost")
os.environ.setdefault("FUSIONPBX_API_KEY", "test-api-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

# Keep file logging writable outside containers.
os.environ.setdefault("BACKEND_LOG_FILE", "backend.log")
