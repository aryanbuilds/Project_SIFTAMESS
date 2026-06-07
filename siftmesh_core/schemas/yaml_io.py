"""YAML <-> Pydantic model round-trip helpers (C3 / C5).

Task contracts and workflows are authored in YAML; these helpers parse YAML into
a validated model (``model_validate``) and serialize a model back to YAML through
its JSON-mode dump (so custom serializers like the UTC-``Z`` datetime serializer
apply). Parsing uses ``yaml.safe_load`` — case data is never trusted to construct
arbitrary Python objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml

from siftmesh_core.schemas._base import StrictModel

ModelT = TypeVar("ModelT", bound=StrictModel)


def load_yaml_model(model_cls: type[ModelT], text: str) -> ModelT:
    """Validate a YAML document into ``model_cls``."""
    return model_cls.model_validate(yaml.safe_load(text))


def read_yaml_model(model_cls: type[ModelT], path: Path | str) -> ModelT:
    """Validate a YAML file into ``model_cls``."""
    return load_yaml_model(model_cls, Path(path).read_text(encoding="utf-8"))


def dump_yaml_model(model: StrictModel) -> str:
    """Serialize a model to a YAML document (UTC-Z applied; key order preserved)."""
    return yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)
