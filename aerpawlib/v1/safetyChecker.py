"""
safetyChecker module
Provides a proxy for the safety module for backward compatibility.
"""

import warnings
from .safety import *

# Issue a deprecation warning
warnings.warn(
    "aerpawlib.v1.safetyChecker is deprecated, use aerpawlib.v1.safety instead",
    DeprecationWarning,
    stacklevel=2,
)
