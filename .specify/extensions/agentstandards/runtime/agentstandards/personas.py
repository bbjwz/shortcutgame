from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .models import PersonaRegistry


@lru_cache(maxsize=1)
def load_personas() -> PersonaRegistry:
    path = Path(__file__).with_name("personas.yml")
    return PersonaRegistry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
