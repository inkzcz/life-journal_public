"""Process settings; invalid security-switch values fail closed at startup."""
import os
from dataclasses import dataclass
from pathlib import Path


def boolean(name, default):
    value = os.getenv(name, default).lower()
    if value not in {'true', 'false'}:
        raise ValueError(f'{name} must be true or false')
    return value == 'true'


@dataclass(frozen=True)
class Settings:
    cookie_secure: bool
    media_dir: Path
    dynamic_blog_enabled: bool  # Deprecated constructor compatibility only; never an authorization gate.

    @classmethod
    def from_env(cls):
        return cls(boolean('COOKIE_SECURE', 'true'),
                   Path(os.getenv('MEDIA_DIR', '/data/media')),
                   True)  # Phase 4A ignores the retired dynamic feature flag.
