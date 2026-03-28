"""
Pytest configuration for the backend test suite.

Adds the backend root directory to sys.path so test modules can import
application modules (schemas, models, utils, storage, etc.) directly.
"""

import sys
import os

# Add the backend root (parent of tests/) to sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

# Set JWT_SECRET for tests that import auth utilities
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")
