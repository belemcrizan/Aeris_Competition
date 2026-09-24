"""YAML loading with ``!include`` tags kept as unresolved references.

The harness resolves ``!include <path>`` relative to the directory of the file that
contains the tag. We parse the tag into :class:`IncludeRef` so the validator can check
the path before anything is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class IncludeRef:
    path: str


class _IncludeLoader(yaml.SafeLoader):
    pass


class DuplicateKeyError(yaml.YAMLError):
    pass


def _include_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> IncludeRef:
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(None, None, "!include expects a scalar path", node.start_mark)
    return IncludeRef(str(loader.construct_scalar(node)).strip())


def _mapping_without_duplicates(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise DuplicateKeyError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_IncludeLoader.add_constructor("!include", _include_constructor)
_IncludeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates)


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_IncludeLoader)  # noqa: S506 - SafeLoader subclass


def load_yaml_file(path: Path) -> Any:
    return load_yaml(path.read_text(encoding="utf-8"))
