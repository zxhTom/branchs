#!/usr/bin/env python3
"""Build script for branchs (executables and python packages)."""

import os
import shutil
import subprocess
import sys


def run_cmd(cmd, check=True):
    print(f"==> Running: {cmd}")
    res = subprocess.run(cmd, shell=True)
    if check and res.returncode != 0:
        print(f"Error: command failed with code {res.returncode}")
        sys.exit(res.returncode)


def clean():
    print("==> Cleaning old build artifacts...")
    for dir_name in ["build", "dist", "*.egg-info"]:
        if os.path.exists(dir_name):
            if os.path.isdir(dir_name):
                shutil.rmtree(dir_name, ignore_errors=True)
            else:
                os.remove(dir_name)


def build_executables():
    print("==> Building standalone executables (CLI & GUI) with PyInstaller...")
    run_cmd("pyinstaller --clean branchs.spec")
    print("\nExecutables generated successfully in `dist/`:")
    if os.path.exists("dist"):
        for item in os.listdir("dist"):
            print(f"  - dist/{item}")


def build_wheel():
    print("==> Building Python wheel and sdist...")
    run_cmd(f"{sys.executable} -m pip install --upgrade build")
    run_cmd(f"{sys.executable} -m build")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build branchs binaries and distribution packages")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before building")
    parser.add_argument("--exe-only", action="store_true", help="Only build PyInstaller executables")
    parser.add_argument("--wheel-only", action="store_true", help="Only build pip wheel/sdist")
    args = parser.parse_args()

    if args.clean:
        clean()

    if args.exe_only:
        build_executables()
    elif args.wheel_only:
        build_wheel()
    else:
        build_executables()
        build_wheel()


if __name__ == "__main__":
    main()
