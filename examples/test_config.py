"""Test config loading."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from elib.utils.config import Config

print("Testing config loading...")
print(f"Looking for config in: {Path.cwd()}")
print()

try:
    config = Config.load()
    print("✓ Config loaded successfully!")
    print(f"  Email: {config.ncbi_email}")
    print(f"  API Key: {'✓' if config.ncbi_api_key else '✗'}")
    print(f"  Database: {config.database_path}")
    print(f"  Target Dir: {config.target_directory}")
except FileNotFoundError:
    print("✗ config.yaml not found")
    print(f"  Current directory: {Path.cwd()}")
except Exception as e:
    print(f"✗ Error loading config: {e}")
