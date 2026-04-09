"""
AERPAW vehicle-control library.

This package keeps a lazy compatibility surface for legacy
``import aerpawlib`` usage while the maintained APIs live under
``aerpawlib.v1`` and ``aerpawlib.v2``.

For new code, prefer explicit versioned imports such as
``from aerpawlib.v1 import Drone`` or ``from aerpawlib.v2 import Drone``.
"""

__author__ = "John Kesler and Julian Reder"


# Lazy load v1 API only when accessed
# New code should be written using aerpawlib.v1.*, but legacy code uses aerpawlib.*.
# We then lazy load the v1 module on first access.
_v1_loaded = False
_loading = False


def __getattr__(name):
    global _v1_loaded, _loading
    if _loading:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    if not _v1_loaded:
        _loading = True
        try:
            from . import v1

            # Import all from v1 into globals
            for attr in dir(v1):
                if not attr.startswith("_"):
                    globals()[attr] = getattr(v1, attr)
            _v1_loaded = True
        finally:
            _loading = False
    value = globals().get(name)
    if value is None and name not in globals():
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    return value
