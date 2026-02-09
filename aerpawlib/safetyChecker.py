"""
Safety checker module for aerpawlib.

This module has been moved to aerpawlib.v1.safety for backward compatibility.
The original safetyChecker module is deprecated and will be removed in future releases.

This file provides backward compatibility by re-exporting from v1.
For new code, consider using aerpawlib.v2.safety_checker for async support.
"""

import warnings

# Issue a deprecation warning for direct imports
warnings.warn(
    "Importing from aerpawlib.v1.safetyChecker is deprecated. "
    "Use 'from aerpawlib.v1.safety import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from v1 for backward compatibility
from .v1.safety import *
