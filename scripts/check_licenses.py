#!/usr/bin/env python3
# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
License verification script for Cross-File Context Links.

Verifies that all dependencies have compatible licenses (no GPL/AGPL/LGPL).
Generates THIRD_PARTY_LICENSES.txt documenting all dependency licenses.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

# Prohibited licenses (incompatible with proprietary code)
PROHIBITED_LICENSES = {
    "GPL",
    "GPLv2",
    "GPLv3",
    "GPL-2.0",
    "GPL-3.0",
    "GNU GPL",
    "GNU GPLv2",
    "GNU GPLv3",
    "AGPL",
    "AGPLv3",
    "AGPL-3.0",
    "GNU AGPL",
    "GNU AGPLv3",
    "LGPL",
    "LGPLv2",
    "LGPLv3",
    "LGPL-2.0",
    "LGPL-2.1",
    "LGPL-3.0",
    "GNU LGPL",
    "GNU LGPLv2",
    "GNU LGPLv3",
}

# Permissible licenses (compatible with proprietary code)
PERMISSIBLE_LICENSES = {
    "MIT",
    "MIT License",
    "BSD",
    "BSD License",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache",
    "Apache 2.0",
    "Apache License 2.0",
    "Apache Software License",
    "ISC",
    "ISC License",
    "PSF",
    "Python Software Foundation License",
    "UNKNOWN",  # Allow unknown licenses with a warning
}


def run_pip_licenses() -> List[Dict[str, str]]:
    """Run pip-licenses and return the output as a list of dictionaries.

    Returns:
        List of dictionaries with package license information
    """
    try:
        result = subprocess.run(
            ["pip-licenses", "--format=json", "--with-authors", "--with-urls"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running pip-licenses: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing pip-licenses output: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: pip-licenses not found. Please install it with: pip install pip-licenses",
            file=sys.stderr,
        )
        sys.exit(1)


def check_license_compatibility(license_name: str) -> bool:
    """Check if a license is compatible with proprietary code.

    Args:
        license_name: Name of the license

    Returns:
        True if compatible, False if prohibited
    """
    # Normalize license name for comparison
    normalized = license_name.strip()

    # Check if it's a prohibited license
    return all(prohibited.lower() not in normalized.lower() for prohibited in PROHIBITED_LICENSES)


def generate_third_party_licenses(packages: List[Dict[str, str]]) -> str:
    """Generate THIRD_PARTY_LICENSES.txt content.

    Args:
        packages: List of package information dictionaries

    Returns:
        Content for THIRD_PARTY_LICENSES.txt
    """
    lines = [
        "Third-Party Licenses",
        "=" * 80,
        "",
        "This file lists all third-party dependencies and their licenses.",
        "",
        "=" * 80,
        "",
    ]

    for pkg in sorted(packages, key=lambda x: x["Name"].lower()):
        lines.append(f"Package: {pkg['Name']}")
        lines.append(f"Version: {pkg['Version']}")
        lines.append(f"License: {pkg['License']}")

        if pkg.get("Author"):
            lines.append(f"Author: {pkg['Author']}")

        if pkg.get("URL"):
            lines.append(f"URL: {pkg['URL']}")

        lines.append("-" * 80)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main function to check licenses and generate documentation.

    Returns:
        0 if all licenses are compatible, 1 if prohibited licenses found
    """
    print("Checking dependency licenses...")
    packages = run_pip_licenses()

    prohibited_packages: List[Dict[str, str]] = []
    unknown_packages: List[Dict[str, str]] = []
    compatible_packages: List[Dict[str, str]] = []

    for pkg in packages:
        license_name = pkg.get("License", "UNKNOWN")

        if not check_license_compatibility(license_name):
            prohibited_packages.append(pkg)
        elif license_name == "UNKNOWN":
            unknown_packages.append(pkg)
        else:
            compatible_packages.append(pkg)

    # Print summary
    print(f"\nTotal packages: {len(packages)}")
    print(f"Compatible licenses: {len(compatible_packages)}")
    print(f"Unknown licenses: {len(unknown_packages)}")
    print(f"Prohibited licenses: {len(prohibited_packages)}")

    # Warn about unknown licenses
    if unknown_packages:
        print("\n⚠️  WARNING: Packages with unknown licenses:")
        for pkg in unknown_packages:
            print(f"  - {pkg['Name']} ({pkg['Version']})")
        print("  Please verify these licenses manually.")

    # Error on prohibited licenses
    if prohibited_packages:
        print("\n❌ ERROR: Packages with prohibited licenses found:")
        for pkg in prohibited_packages:
            print(f"  - {pkg['Name']} ({pkg['Version']}): {pkg['License']}")
        print("\nProhibited licenses (GPL/AGPL/LGPL) are incompatible with proprietary code.")
        print("Please remove these dependencies or find alternatives.")
        return 1

    # Generate THIRD_PARTY_LICENSES.txt
    print("\nGenerating THIRD_PARTY_LICENSES.txt...")
    third_party_content = generate_third_party_licenses(packages)

    output_path = Path("THIRD_PARTY_LICENSES.txt")
    output_path.write_text(third_party_content, encoding="utf-8")

    print(f"✓ THIRD_PARTY_LICENSES.txt generated at {output_path}")
    print("\n✓ All license checks passed!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
