"""
Deprecated compatibility shim for the v1 safety package.

This module preserves the historical `aerpawlib.v1.safetyChecker` import path
by re-exporting symbols from `aerpawlib.v1.safety`.

Capabilities
- Keep legacy imports working for older scripts and tests.
- Emit a `DeprecationWarning` guiding users to the modern package path.

Notes:
- New code should import from `aerpawlib.v1.safety` directly.
"""

import warnings
from .safety import *

# Issue a deprecation warning
warnings.warn(
    "aerpawlib.v1.safetyChecker is deprecated, use aerpawlib.v1.safety instead",
    DeprecationWarning,
    stacklevel=2,
)
