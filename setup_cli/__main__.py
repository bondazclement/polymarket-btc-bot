"""
Main entry point for the Polymarket BTC UpDown 5m trading bot setup CLI.

This module provides a 9-step interactive setup process: system checks,
geo/connectivity, dependency install, .env creation, CLOB test, benchmarks,
pipeline validation, and final report.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from typing import Dict, List

from setup_cli.benchmark import run_benchmarks
from setup_cli.geo_checker import run_geo_checks
from setup_cli.validator import run_validation


async def main() -> None:
    """Main function to run the setup CLI."""
    parser = argparse.ArgumentParser(
        description="Polymarket BTC UpDown 5m Trading Bot Setup CLI"
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip system checks and proceed with installation",
    )
    parser.add_argument(
        "--skip-benchmarks",
        action="store_true",
        help="Skip benchmarks and proceed with installation",
    )

    args = parser.parse_args()

    report = await run_setup(args.skip_checks, args.skip_benchmarks)

    # Final report
    print("\n" + "=" * 50)
    print("SETUP COMPLETE")
    print("=" * 50)
    for step, status in report.items():
        symbol = "\u2705" if status else "\u274c"
        print(f"{symbol} {step}")

    if all(report.values()):
        print("\nAll steps completed successfully!")
        print("You can now run: python -m src --mode dry-run")
    else:
        print("\nSome steps failed. Please review the errors above.")


async def run_setup(skip_checks: bool, skip_benchmarks: bool) -> Dict[str, bool]:
    """Run the full setup process.

    Args:
        skip_checks: Whether to skip system checks.
        skip_benchmarks: Whether to skip benchmarks.

    Returns:
        Dictionary with the status of each setup step.
    """
    report: Dict[str, bool] = {}

    # Step 1: System requirements
    if not skip_checks:
        report["1. System Checks"] = await check_system_requirements()
    else:
        report["1. System Checks"] = True

    # Step 2: Geo & connectivity checks
    geo_passed, _ = await run_geo_checks()
    report["2. Geo & Connectivity"] = geo_passed

    # Step 3: Install dependencies
    report["3. Install Dependencies"] = await install_dependencies()

    # Step 4: Create .env file
    report["4. Create .env File"] = await create_env_file()

    # Step 5: Test CLOB connection
    report["5. Test CLOB Connection"] = await test_clob_connection()

    # Step 6: Test CLOB auth (if credentials available)
    report["6. Test CLOB Auth"] = await test_clob_auth()

    # Step 7: Run benchmarks
    if not skip_benchmarks:
        report["7. Benchmarks"] = await run_benchmarks()
    else:
        report["7. Benchmarks"] = True

    # Step 8: Pipeline validation
    val_passed, _ = await run_validation()
    report["8. Pipeline Validation"] = val_passed

    # Step 9: Summary
    report["9. Ready"] = all(
        v for k, v in report.items() if k != "9. Ready"
    )

    return report


async def check_system_requirements() -> bool:
    """Check if the system meets the requirements.

    Returns:
        True if all requirements are met, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 1: SYSTEM REQUIREMENTS")
    print("=" * 50)

    checks: List[bool] = []

    # Python version
    python_version = sys.version_info
    if python_version >= (3, 11):
        print(f"  \u2705 Python {python_version.major}.{python_version.minor}")
        checks.append(True)
    else:
        print(f"  \u274c Python {python_version.major}.{python_version.minor} (need >= 3.11)")
        checks.append(False)

    # pip
    try:
        subprocess.run(["pip", "--version"], check=True, capture_output=True)
        print("  \u2705 pip installed")
        checks.append(True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  \u274c pip not found")
        checks.append(False)

    # git
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        print("  \u2705 git installed")
        checks.append(True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("  \u274c git not found")
        checks.append(False)

    return all(checks)


async def install_dependencies() -> bool:
    """Install the required dependencies.

    Returns:
        True if dependencies were installed successfully, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 3: INSTALLING DEPENDENCIES")
    print("=" * 50)

    try:
        subprocess.run(["pip", "install", "-e", "."], check=True)
        print("  \u2705 Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  \u274c Failed: {e}")
        return False


async def create_env_file() -> bool:
    """Create the .env file interactively.

    Returns:
        True if the .env file was created successfully, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 4: .env FILE")
    print("=" * 50)

    if os.path.exists(".env"):
        print("  \u2705 .env file already exists")
        return True

    env_vars = {
        "POLYMARKET_PRIVATE_KEY": "Private key for the EOA on Polygon",
        "POLYMARKET_FUNDER": "Proxy wallet address on Polymarket",
        "POLYMARKET_API_KEY": "API key for Polymarket L2",
        "POLYMARKET_API_SECRET": "API secret for Polymarket L2",
        "POLYMARKET_PASSPHRASE": "Passphrase for Polymarket L2",
        "POLYGON_RPC_URL": "RPC URL for Polygon network",
    }

    env_content = ""
    for var, description in env_vars.items():
        value = input(f"  Enter {description}: ")
        env_content += f"{var}={value}\n"

    try:
        with open(".env", "w") as f:
            f.write(env_content)
        print("  \u2705 .env file created")
        return True
    except Exception as e:
        print(f"  \u274c Failed to create .env: {e}")
        return False


async def test_clob_connection() -> bool:
    """Test the connection to the Polymarket CLOB (Level 0, no auth).

    Returns:
        True if the connection test was successful, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 5: CLOB CONNECTION (Level 0)")
    print("=" * 50)

    try:
        from py_clob_client.client import ClobClient

        client = ClobClient(host="https://clob.polymarket.com")
        ok = client.get_ok()
        server_time = client.get_server_time()
        if ok == "OK":
            print(f"  \u2705 CLOB OK (server time: {server_time})")
            return True
        else:
            print(f"  \u274c Unexpected response: {ok}")
            return False
    except Exception as e:
        print(f"  \u274c CLOB test failed: {e}")
        return False


async def test_clob_auth() -> bool:
    """Test CLOB authenticated access (Level 1+).

    Returns:
        True if auth works or no credentials configured, False on auth failure.
    """
    print("\n" + "=" * 50)
    print("STEP 6: CLOB AUTH (Level 1)")
    print("=" * 50)

    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    funder = os.getenv("POLYMARKET_FUNDER", "")

    if not private_key or not funder:
        print("  \u26a0\ufe0f  Skipped (no credentials in .env)")
        return True

    try:
        from py_clob_client.client import ClobClient

        client = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            signature_type=0,
            funder=funder,
        )

        api_key = os.getenv("POLYMARKET_API_KEY", "")
        api_secret = os.getenv("POLYMARKET_API_SECRET", "")
        passphrase = os.getenv("POLYMARKET_PASSPHRASE", "")

        if api_key and api_secret and passphrase:
            from py_clob_client.clob_types import ApiCreds

            client.set_api_creds(
                ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=passphrase,
                )
            )
            print("  \u2705 API credentials loaded")
        else:
            creds = client.create_or_derive_api_creds()
            client.set_api_creds(creds)
            print("  \u2705 API credentials derived")

        return True
    except Exception as e:
        print(f"  \u274c Auth test failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
