"""
Dependency Manager for Kiwiscribe

This script provides a centralized way to check for dependency conflicts and
perform safe package updates, ensuring that critical Google Cloud dependencies
are not affected.

Package operations use 'uv pip' (works with uv-created venvs that have no pip).
"""

import importlib.metadata
import json
import shutil
import subprocess
import sys

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# The requirements file is now the single source of truth.
REQUIREMENTS_FILE = "requirements_build.txt"


def find_uv():
    """Locate the uv executable on PATH."""
    uv_path = shutil.which("uv")
    if not uv_path:
        print(
            "Error: 'uv' was not found on PATH. Install it from https://docs.astral.sh/uv/",
            file=sys.stderr,
        )
        sys.exit(1)
    return uv_path


UV_EXE = find_uv()


def uv_pip_argv(*args):
    """Build a 'uv pip ...' command targeting the current Python environment."""
    return [UV_EXE, "pip", *args, "--python", sys.executable]


try:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion, Version
except ModuleNotFoundError:
    print("'packaging' is missing. Installing it now...", file=sys.stderr)
    try:
        subprocess.run(
            uv_pip_argv("install", "packaging"),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        from packaging.version import InvalidVersion, Version
    except Exception as e:
        print(f"Error: Failed to install required dependency 'packaging': {e}", file=sys.stderr)
        sys.exit(1)


def load_critical_dependencies(filepath):
    """Loads and parses the requirements from the source file."""
    dependencies = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Ignore comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Handle potential comments on the same line
                line = line.split("#")[0].strip()
                if not line:
                    continue

                try:
                    req = Requirement(line)
                    # Store name and specifier separately
                    dependencies[req.name] = str(req.specifier) if req.specifier else ""
                except Exception as e:
                    print(f"Warning: Could not parse line '{line}': {e}", file=sys.stderr)
    except FileNotFoundError:
        print(f"Error: The requirements file '{filepath}' was not found.", file=sys.stderr)
        sys.exit(1)
    return dependencies


# Load the dependencies dynamically
CRITICAL_DEPENDENCIES = load_critical_dependencies(REQUIREMENTS_FILE)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def print_section(title):
    """Prints a formatted section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def run_uv_pip_command(command, parse_json=True):
    """Runs a 'uv pip' command against the current Python and returns the output."""
    cmd = uv_pip_argv(*command)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        output = result.stdout.strip()
        if not output:
            return [] if parse_json else ""

        if parse_json:
            return json.loads(output)
        return output

    except subprocess.CalledProcessError as e:
        print(f"Error running '{' '.join(cmd)}'. Exit code: {e.returncode}", file=sys.stderr)
        print(f"  - Stderr: {e.stderr.strip()}", file=sys.stderr)
        print(f"  - Stdout: {e.stdout.strip()}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from '{' '.join(cmd)}': {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: 'uv' command not found. Is uv installed and on PATH?", file=sys.stderr)
        return None


def get_installed_packages():
    """
    Gets a dictionary of all installed packages and their versions.
    Tries 'uv pip list --format=json' first, then falls back to 'uv pip freeze'.
    """
    installed_list = run_uv_pip_command(["list", "--format=json"])
    if installed_list is not None:
        return {canonicalize_name(pkg["name"]): pkg["version"] for pkg in installed_list}

    # Fallback to freeze if the primary method fails
    print("\nWarning: 'uv pip list --format=json' failed. Falling back to 'uv pip freeze'.", file=sys.stderr)
    freeze_output = run_uv_pip_command(["freeze"], parse_json=False)
    if freeze_output is None:
        return {}

    packages = {}
    for line in freeze_output.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            # Handle packages installed in editable mode (-e)
            if "-e" in line:
                # A more robust way to find the package name might be needed
                # For now, this handles common cases like '-e git+...#egg=package_name'
                if "#egg=" in line:
                    name_part = line.split("#egg=")[-1]
                    packages[canonicalize_name(name_part)] = "editable"
            # Handle standard 'package==version' format
            elif "==" in line:
                parts = line.split("==")
                packages[canonicalize_name(parts[0])] = parts[1]
    return packages


def find_blocking_requirements(package_name, candidate_version):
    """
    Find installed packages whose requirements exclude candidate_version for package_name.

    Returns a list of human-readable reasons, e.g.:
      "pydantic 2.13.4 requires pydantic-core==2.46.4"
    """
    target = canonicalize_name(package_name)
    try:
        candidate = Version(candidate_version)
    except InvalidVersion:
        return []

    blockers = []
    for dist in importlib.metadata.distributions():
        requires = dist.requires or []
        dist_name = dist.metadata.get("Name") or dist.name
        dist_version = dist.version
        for req_str in requires:
            try:
                req = Requirement(req_str)
            except Exception:
                continue
            if canonicalize_name(req.name) != target:
                continue
            if req.marker is not None:
                try:
                    if not req.marker.evaluate():
                        continue
                except Exception:
                    # If marker evaluation fails, still treat the requirement as relevant.
                    pass
            if not req.specifier or candidate in req.specifier:
                continue
            blockers.append(
                f"{dist_name} {dist_version} requires {req.name}{req.specifier}"
            )
    return blockers


def classify_outdated_non_critical(outdated_packages, critical_names_lower):
    """
    Split outdated non-critical packages into upgradable vs blocked-by-pin.

    Returns:
      upgradable: list of package names
      blocked: list of (name, current, latest, reasons)
    """
    upgradable = []
    blocked = []
    for pkg in outdated_packages:
        name = pkg["name"]
        if canonicalize_name(name) in critical_names_lower:
            continue
        current = pkg.get("version", "?")
        latest = pkg.get("latest_version") or pkg.get("latest", "?")
        blockers = find_blocking_requirements(name, latest)
        if blockers:
            blocked.append((name, current, latest, blockers))
        else:
            upgradable.append(name)
    return upgradable, blocked


def report_remaining_outdated():
    """After an update, warn about packages that are still outdated and why."""
    remaining = run_uv_pip_command(["list", "--outdated", "--format=json"])
    if remaining is None:
        return
    if not remaining:
        return

    print("\n[WARNING] Some packages remain outdated after the update:")
    for pkg in remaining:
        name = pkg["name"]
        current = pkg.get("version", "?")
        latest = pkg.get("latest_version") or pkg.get("latest", "?")
        blockers = find_blocking_requirements(name, latest)
        print(f"  - {name}: {current} -> {latest}")
        if blockers:
            for reason in blockers:
                print(f"      blocked by: {reason}")
            print("      Updating it would break dependency compatibility.")
        else:
            print("      No hard pin detected; it may have been held back by the resolver.")


# ==============================================================================
# CORE LOGIC
# ==============================================================================


def check_dependencies():
    """
    Checks the current environment for conflicts with critical dependencies.
    """
    print_section("Checking Dependencies for Conflicts")
    installed_packages = get_installed_packages()
    if not installed_packages:
        print("Could not retrieve installed packages.", file=sys.stderr)
        return

    conflicts = []
    print("Verifying critical dependency constraints...")
    print(f"{'Package':<35} {'Required':<20} {'Installed':<15} {'Status':<10}")
    print("-" * 80)

    for name, specifier in CRITICAL_DEPENDENCIES.items():
        req = Requirement(f"{name}{specifier}")
        installed_version_str = installed_packages.get(req.name.lower())

        status = "[OK]"
        if not installed_version_str:
            status = "[NOT FOUND]"
            conflicts.append(f"{req.name} is not installed.")
        else:
            try:
                installed_version = Version(installed_version_str)
                if installed_version not in req.specifier:
                    status = "[CONFLICT]"
                    conflicts.append(
                        f"Conflict for {req.name}: Version {installed_version} is installed, "
                        f"but requirement is '{specifier}'."
                    )
            except InvalidVersion:
                status = "[UNKNOWN VERSION]"
                conflicts.append(
                    f"Could not validate version for {req.name}: '{installed_version_str}' is not PEP 440 compliant."
                )

        print(f"{req.name:<35} {str(req.specifier):<20} {installed_version_str or 'N/A':<15} {status:<10}")

    if conflicts:
        print("\n[WARNING] Conflicts Detected!")
        for conflict in conflicts:
            print(f"  - {conflict}")
        print("\nTo fix conflicts, run: python dependency_manager.py update")
    else:
        print("\n[OK] No conflicts detected. All critical dependencies meet their constraints.")


def update_packages():
    """
    Updates packages, respecting version constraints for critical dependencies.
    Allows updates to critical packages as long as they satisfy their version constraints.
    """
    print_section("Performing Package Update")

    # 0. Check for and handle problematic packages (like accidentally installed "update")
    print("Checking for problematic packages...")
    installed_list = run_uv_pip_command(["list", "--format=json"])
    problematic_packages = []
    if installed_list:
        for pkg in installed_list:
            name_lower = pkg["name"].lower()
            # Check if this is a known problematic package that shouldn't be here
            if name_lower == "update" and name_lower not in {n.lower() for n in CRITICAL_DEPENDENCIES.keys()}:
                problematic_packages.append(pkg["name"])

    if problematic_packages:
        print(f"\n[WARNING] Found problematic packages: {', '.join(problematic_packages)}")
        print("These packages will be uninstalled to avoid conflicts.")
        try:
            choice = input("Uninstall these packages? (y/n): ").lower()
            if choice == "y":
                subprocess.run(
                    uv_pip_argv("uninstall", "-y", *problematic_packages),
                    check=True,
                )
                print(f"[OK] Removed problematic packages: {', '.join(problematic_packages)}")
            else:
                print("[WARNING] Keeping problematic packages. Conflicts may occur.")
        except (EOFError, KeyboardInterrupt):
            print("\nSkipping removal of problematic packages.")
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] Failed to remove problematic packages. Exit code: {e.returncode}", file=sys.stderr)

    # 1. Get all outdated packages
    print("\nChecking for outdated packages...")
    outdated_packages = run_uv_pip_command(["list", "--outdated", "--format=json"])

    # 2. Separate packages into categories based on constraints
    critical_to_upgrade = []  # Critical packages that can be upgraded (have >= constraints)
    critical_to_pin = []  # Critical packages with exact pinning (== constraints)
    non_critical_to_update = []  # Non-critical packages to update
    non_critical_blocked = []  # Outdated but pinned by another installed package

    if outdated_packages is None:
        print("\nWarning: Could not retrieve the list of outdated packages.", file=sys.stderr)
        print("Proceeding to install/update critical dependencies only.", file=sys.stderr)
        # Process critical dependencies even if we can't check outdated packages
        for name, spec in CRITICAL_DEPENDENCIES.items():
            if "==" in spec and not (">=" in spec or "~=" in spec):
                critical_to_pin.append(f"{name}{spec}")
            else:
                critical_to_upgrade.append(name)
    elif not outdated_packages:
        print("[OK] No outdated packages found.")
        # Process critical dependencies to ensure they're up to date
        for name, spec in CRITICAL_DEPENDENCIES.items():
            if "==" in spec and not (">=" in spec or "~=" in spec):
                critical_to_pin.append(f"{name}{spec}")
            else:
                critical_to_upgrade.append(name)
    else:
        critical_names_lower = {canonicalize_name(name): name for name in CRITICAL_DEPENDENCIES.keys()}

        # Process critical dependencies
        for name, spec in CRITICAL_DEPENDENCIES.items():
            req_str = f"{name}{spec}"

            # Check if this critical package has an exact version pin (==)
            if "==" in spec and not (">=" in spec or "~=" in spec):
                # Exact pin - maintain the constraint exactly as specified
                critical_to_pin.append(req_str)
            else:
                # Has >= or other flexible constraints - upgrade to latest
                # For flexible constraints, upgrade without constraint first, then verify
                # This ensures we get the latest version that still satisfies requirements
                critical_to_upgrade.append(name)  # Upgrade without constraint to get latest

        # Process non-critical outdated packages, skipping ones pinned by dependencies
        non_critical_to_update, non_critical_blocked = classify_outdated_non_critical(
            outdated_packages, critical_names_lower
        )

    # 3. Display proposed changes
    print("\nThe following actions will be taken:")

    if critical_to_upgrade:
        print("\n  - CRITICAL packages (with flexible constraints) will be upgraded:")
        for pkg in critical_to_upgrade:
            print(f"    - {pkg}")

    if critical_to_pin:
        print("\n  - CRITICAL packages (with exact pinning) will be set to required versions:")
        for pkg in critical_to_pin:
            print(f"    - {pkg}")

    if non_critical_to_update:
        print("\n  - NON-CRITICAL packages will be upgraded to their latest versions:")
        for pkg in non_critical_to_update:
            print(f"    - {pkg}")

    if non_critical_blocked:
        print("\n  - NON-CRITICAL packages SKIPPED (pinned by another installed package):")
        for name, current, latest, blockers in non_critical_blocked:
            print(f"    - {name}: {current} -> {latest}")
            for reason in blockers:
                print(f"        blocked by: {reason}")
            print("        Updating it would break dependency compatibility.")

    if not critical_to_upgrade and not critical_to_pin and not non_critical_to_update:
        if non_critical_blocked:
            print("\n  - No safe updates available (only blocked outdated packages remain).")
        else:
            print("\n  - No updates needed.")

    # 4. Ask for confirmation
    try:
        choice = input("\nDo you want to proceed with this update? (y/n): ").lower()
        if choice != "y":
            print("Update cancelled.")
            return
    except (EOFError, KeyboardInterrupt):
        print("\nUpdate cancelled.")
        return

    # 5. Execute the installation
    print("\nInstalling packages...")

    # Build list of packages to upgrade (without constraints for flexible ones)
    upgrade_packages = []

    # For critical packages with flexible constraints, upgrade without constraint to get latest
    upgrade_packages.extend(critical_to_upgrade)

    # For non-critical packages, upgrade to latest
    upgrade_packages.extend(non_critical_to_update)

    # Upgrade packages without constraints (this ensures latest versions)
    if upgrade_packages:
        try:
            subprocess.run(
                uv_pip_argv("install", "--upgrade", *upgrade_packages),
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] Failed to upgrade packages. Exit code: {e.returncode}", file=sys.stderr)
            return

    # Now ensure all critical packages meet their constraints
    # This includes both pinned packages and verification of flexible constraints
    # For pinned packages, install with exact version
    # For flexible constraints, install with constraint (won't downgrade if already satisfied)
    all_critical_packages = [f"{name}{spec}" for name, spec in CRITICAL_DEPENDENCIES.items()]

    if all_critical_packages:
        try:
            subprocess.run(
                uv_pip_argv("install", *all_critical_packages),
                check=True,
            )
            check_result = subprocess.run(
                uv_pip_argv("check"),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if check_result.returncode == 0:
                print("\n[OK] Packages updated successfully and no dependency conflicts were reported by uv pip check.")
            else:
                print("\n[WARNING] Packages updated, but uv pip check reported dependency issues:")
                if check_result.stdout.strip():
                    print(check_result.stdout.strip())
                if check_result.stderr.strip():
                    print(check_result.stderr.strip(), file=sys.stderr)
            report_remaining_outdated()
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] uv pip install command failed with exit code {e.returncode}", file=sys.stderr)
            print("Some packages may have been upgraded but constraints may not be met.", file=sys.stderr)
        except Exception as e:
            print(f"\n[ERROR] An unexpected error occurred: {e}", file=sys.stderr)
    elif not upgrade_packages:
        print("No packages to install or update.")
        if non_critical_blocked:
            print("\nSkipped outdated packages pinned by dependencies (see list above).")
        report_remaining_outdated()


def main():
    """Main entry point for the script."""
    action = None
    if len(sys.argv) >= 2 and sys.argv[1] in ["check", "update"]:
        action = sys.argv[1]
    else:
        print("Usage: python dependency_manager.py [check|update]")
        # If no valid argument is provided, prompt the user interactively.
        try:
            choice = input("Please choose an action ('check' or 'update'): ").lower()
            if choice in ["check", "update"]:
                action = choice
            else:
                print("Invalid action. Exiting.")
                sys.exit(1)
        except (EOFError, KeyboardInterrupt):
            print("\nAction cancelled by user. Exiting.")
            sys.exit(0)  # Exit gracefully

    if action == "check":
        check_dependencies()
    elif action == "update":
        update_packages()


if __name__ == "__main__":
    main()
