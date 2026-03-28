"""
Recipe models and helpers for repeatable Misata runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from misata.schema import SchemaConfig


class RecipeSpec(BaseModel):
    """Minimal recipe wrapper around existing generation inputs."""

    name: str
    story: Optional[str] = None
    schema_config: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    output_dir: str = "./generated_data"
    db_url: Optional[str] = None
    validation: bool = False
    quality: bool = False
    audit: bool = False

    @model_validator(mode="after")
    def validate_inputs(self) -> "RecipeSpec":
        if not self.story and not self.schema_config:
            raise ValueError("Recipe must include either 'story' or 'schema_config'.")
        if self.story and self.schema_config:
            raise ValueError("Recipe cannot include both 'story' and 'schema_config'.")
        return self

    def to_schema_config(self) -> Optional[SchemaConfig]:
        """Parse the embedded schema config if present."""
        if self.schema_config is None:
            return None
        return SchemaConfig(**self.schema_config)


class RunManifest(BaseModel):
    """Machine-readable metadata for a recipe run."""

    recipe_name: str
    misata_version: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    seed: Optional[int] = None
    output_dir: str
    db_url: Optional[str] = None
    tables: Dict[str, int] = Field(default_factory=dict)
    total_rows: int = 0
    artifacts: Dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


def load_recipe(path: str | Path) -> RecipeSpec:
    """Load a YAML or JSON recipe file."""
    recipe_path = Path(path)
    content = recipe_path.read_text(encoding="utf-8")
    if recipe_path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        data = yaml.safe_load(content)
    return RecipeSpec(**(data or {}))


def save_recipe(recipe: RecipeSpec, path: str | Path) -> Path:
    """Save a recipe as YAML."""
    recipe_path = Path(path)
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    payload = recipe.model_dump(exclude_none=True)
    recipe_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return recipe_path


def utc_now() -> str:
    """Return a stable UTC timestamp string."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
