"""
Main entry point for the Polymarket BTC UpDown 5m trading bot setup CLI.

This module provides an interactive setup process to configure the bot,
install dependencies, and run benchmarks.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from typing import Dict, List

from setup_cli.benchmark import run_benchmarks


async def main() -> None:
    """Main function to run the setup CLI."""
    parser = argparse.ArgumentParser(description="Polymarket BTC UpDown 5m Trading Bot Setup CLI")
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

    # Run the setup process
    report = await run_setup(args.skip_checks, args.skip_benchmarks)

    # Print the final report
    print("\n" + "=" * 50)
    print("SETUP COMPLETE")
    print("=" * 50)
    for step, status in report.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {step}")

    if all(report.values()):
        print("\nAll steps completed successfully!")
    else:
        print("\nSome steps failed. Please review the errors above.")


async def run_setup(skip_checks: bool, skip_benchmarks: bool) -> Dict[str, bool]:
    """Run the setup process.

    Args:
        skip_checks: Whether to skip system checks.
        skip_benchmarks: Whether to skip benchmarks.

    Returns:
        Dictionary with the status of each setup step.
    """
    report: Dict[str, bool] = {}

    # Step 1: Check system requirements
    if not skip_checks:
        report["System Checks"] = await check_system_requirements()
    else:
        report["System Checks"] = True

    # Step 2: Install dependencies
    report["Install Dependencies"] = await install_dependencies()

    # Step 3: Create .env file
    report["Create .env File"] = await create_env_file()

    # Step 4: Test CLOB connection
    report["Test CLOB Connection"] = await test_clob_connection()

    # Step 5: Run benchmarks
    if not skip_benchmarks:
        report["Run Benchmarks"] = await run_benchmarks()
    else:
        report["Run Benchmarks"] = True

    return report


async def check_system_requirements() -> bool:
    """Check if the system meets the requirements.

    Returns:
        True if all requirements are met, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 1: CHECKING SYSTEM REQUIREMENTS")
    print("=" * 50)

    checks: List[bool] = []

    # Check Python version
    python_version = sys.version_info
    if python_version >= (3, 11):
        print("✅ Python version >= 3.11")
        checks.append(True)
    else:
        print(f"❌ Python version {python_version} is not supported. Please use Python 3.11 or higher.")
        checks.append(False)

    # Check if pip is installed
    try:
        subprocess.run(["pip", "--version"], check=True, capture_output=True)
        print("✅ pip is installed")
        checks.append(True)
    except subprocess.CalledProcessError:
        print("❌ pip is not installed. Please install pip.")
        checks.append(False)

    # Check if git is installed
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        print("✅ git is installed")
        checks.append(True)
    except subprocess.CalledProcessError:
        print("❌ git is not installed. Please install git.")
        checks.append(False)

    return all(checks)


async def install_dependencies() -> bool:
    """Install the required dependencies.

    Returns:
        True if dependencies were installed successfully, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 2: INSTALLING DEPENDENCIES")
    print("=" * 50)

    try:
        subprocess.run(["pip", "install", "-e", "."], check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


async def create_env_file() -> bool:
    """Create the .env file interactively.

    Returns:
        True if the .env file was created successfully, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 3: CREATING .env FILE")
    print("=" * 50)

    env_vars = {
        "POLYMARKET_PRIVATE_KEY": "Private key for the EOA on Polygon",
        "POLYMARKET_FUNDER": "Address of the proxy wallet on Polymarket",
        "POLYMARKET_API_KEY": "API key for Polymarket L2 credentials",
        "POLYMARKET_API_SECRET": "API secret for Polymarket L2 credentials",
        "POLYMARKET_PASSPHRASE": "Passphrase for Polymarket L2 credentials",
        "POLYGON_RPC_URL": "RPC URL for Polygon network",
    }

    env_content = ""
    for var, description in env_vars.items():
        value = input(f"Enter {description}: ")
        env_content += f"{var}={value}\n"

    try:
        with open(".env", "w") as f:
            f.write(env_content)
        print("✅ .env file created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create .env file: {e}")
        return False


async def test_clob_connection() -> bool:
    """Test the connection to the Polymarket CLOB.

    Uses Level 0 endpoints (no auth required) to validate connectivity.

    Returns:
        True if the connection test was successful, False otherwise.
    """
    print("\n" + "=" * 50)
    print("STEP 4: TESTING CLOB CONNECTION")
    print("=" * 50)

    try:
        from py_clob_client.client import ClobClient

        # Level 0 test: no key/chain_id needed
        client = ClobClient(host="https://clob.polymarket.com")
        ok = client.get_ok()
        server_time = client.get_server_time()
        if ok == "OK":
            print(f"✅ CLOB connection OK (server time: {server_time})")
            return True
        else:
            print(f"❌ CLOB returned unexpected response: {ok}")
            return False
    except Exception as e:
        print(f"❌ CLOB connection test failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
