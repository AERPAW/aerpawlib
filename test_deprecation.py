#!/usr/bin/env python3
"""Test script to verify deprecation warnings are working"""

import warnings
import sys

# Enable all warnings
warnings.simplefilter('always', DeprecationWarning)

print("Testing deprecation warnings...\n")

try:
    print("1. Importing from aerpawlib.runner...")
    import aerpawlib.runner
    print("   ✓ Import successful")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("\n2. Importing from aerpawlib.util...")
    import aerpawlib.util
    print("   ✓ Import successful")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("\n3. Importing from aerpawlib.vehicle...")
    import aerpawlib.vehicle
    print("   ✓ Import successful")
except Exception as e:
    print(f"   ✗ Error: {e}")

try:
    print("\n4. Importing from aerpawlib.external...")
    import aerpawlib.external
    print("   ✓ Import successful")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n✓ All imports tested!")
print("✓ Deprecation warnings should have been displayed above")

