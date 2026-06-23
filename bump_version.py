"""Bump the Kiwiscribe version following semantic-versioning rules.

The single source of truth is ``APP_VERSION`` in ``Kiwiscribe.py``. This script
reads it, increments the requested component (default: patch) and writes the new
value back to both ``Kiwiscribe.py`` and ``kiwiscribe_installer.cfg`` so the
built installer always carries the bumped version.

Usage:
    python bump_version.py [patch|minor|major]

On success the new version is printed to stdout (so the build script can capture
it) and the exit code is 0.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(HERE, "Kiwiscribe.py")
CONFIG_FILE = os.path.join(HERE, "kiwiscribe_installer.cfg")

# Matches: APP_VERSION = "1.0.0"  (single or double quotes)
VERSION_RE = re.compile(r'(APP_VERSION\s*=\s*["\'])(\d+)\.(\d+)\.(\d+)(["\'])')


def bump(version_tuple, part):
    major, minor, patch = version_tuple
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)  # patch (default)


def main():
    part = (sys.argv[1] if len(sys.argv) > 1 else "patch").lower()
    if part not in ("major", "minor", "patch"):
        sys.stderr.write(
            "ERROR: version component must be one of: major, minor, patch\n"
        )
        return 2

    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        source = f.read()

    match = VERSION_RE.search(source)
    if not match:
        sys.stderr.write(
            "ERROR: could not find APP_VERSION = \"x.y.z\" in Kiwiscribe.py\n"
        )
        return 1

    old_version = f"{match.group(2)}.{match.group(3)}.{match.group(4)}"
    new_tuple = bump((int(match.group(2)), int(match.group(3)), int(match.group(4))), part)
    new_version = "{}.{}.{}".format(*new_tuple)

    # Update Kiwiscribe.py
    new_source = VERSION_RE.sub(
        lambda m: f"{m.group(1)}{new_version}{m.group(5)}", source, count=1
    )
    with open(SOURCE_FILE, "w", encoding="utf-8") as f:
        f.write(new_source)

    # Update kiwiscribe_installer.cfg. Replace only the Application 'version='
    # line (the one equal to the current app version) so the [Python] version is
    # never touched.
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = f.read()

    cfg_pattern = re.compile(r'(?m)^(version=)' + re.escape(old_version) + r'\s*$')
    new_config, replaced = cfg_pattern.subn(rf'\g<1>{new_version}', config, count=1)
    if not replaced:
        sys.stderr.write(
            "ERROR: could not find 'version={}' in kiwiscribe_installer.cfg\n".format(
                old_version
            )
        )
        return 1
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(new_config)

    sys.stderr.write(f"Version bumped ({part}): {old_version} -> {new_version}\n")
    # stdout carries ONLY the new version, for the build script to capture.
    print(new_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
