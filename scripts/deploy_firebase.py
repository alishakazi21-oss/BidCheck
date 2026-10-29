#!/usr/bin/env python3
"""
deploy_firebase.py - Prepare and deploy BidCheck to Firebase.

This script:
1. Copies the app/ source code into functions/ (so Cloud Functions can bundle it)
2. Runs firebase deploy

Run from the BidCheck project root:
    python scripts/deploy_firebase.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_DIR = ROOT / "functions"
APP_SRC = ROOT / "app"
APP_DEST = FUNCTIONS_DIR / "app"

def copy_app():
    print("[*] Copying app/ into functions/app/ ...")
    if APP_DEST.exists():
        shutil.rmtree(APP_DEST)
    shutil.copytree(APP_SRC, APP_DEST)
    print(f"   [OK] Copied {len(list(APP_DEST.rglob('*.py')))} Python files")

def deploy():
    print("\n[*] Running firebase deploy ...")
    result = subprocess.run(
        ["firebase", "deploy", "--only", "hosting,functions"],
        cwd=str(ROOT),
        check=False
    )
    if result.returncode != 0:
        print("\n[FAIL] Deployment failed. Check the output above.")
        sys.exit(1)
    print("\n[OK] Firebase deployment complete!")

if __name__ == "__main__":
    copy_app()
    deploy()
