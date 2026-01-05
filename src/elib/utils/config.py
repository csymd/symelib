"""
src/elib/utils/config.py
"""
import yaml

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# ========================================================= #
# Application Configuration Model                           #
# ========================================================= #

class Config(BaseModel):
    """Application configuration"""
    ncbi_email: str
    ncbi_api_key: Optional[str] = None
    database_path: Path = Path("data/elib.db")
    target_directory: Path = Path("~/Documents/elib").expanduser()
    s3_bucket: Optional[str] = None
    rclone_remote: Optional[str] = None
    
    @classmethod
    def load(cls, config_path: Path = Path("config.yaml")) -> "Config":
        """Load configuration from YAML file"""
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f)
                return cls(**data)
        else:
            # Return default config
            return cls(ncbi_email="your.email@example.com")
    
    def save(self, config_path: Path = Path("config.yaml")):
        """Save configuration to YAML file"""
        with open(config_path, 'w') as f:
            yaml.dump(self.dict(), f)
