"""NameNormalizer: translates raw PDF label strings to canonical metric names."""

from __future__ import annotations

from pathlib import Path

import yaml

YAML_PATH = Path(__file__).parent / "canonical_metrics.yaml"


class NameNormalizer:
    """Translates raw PDF label strings → canonical snake_case metric names.

    Two primary use cases:
    1. MetricsBuilder.resolve_metric() calls get_synonyms() to expand the
       search space before returning None.
    2. MetricsBuilder._convert_to_floats() calls is_percentage() to decide
       whether to divide raw "44%" strings by 100.
    """

    def __init__(self, yaml_path: Path = YAML_PATH) -> None:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        self._canonical_to_meta: dict[str, dict] = {}
        self._synonym_to_canonical: dict[str, str] = {}

        for entry in data.get("metrics", []):
            canonical = entry["canonical"]
            self._canonical_to_meta[canonical] = entry

            for syn in entry.get("synonyms", []):
                self._synonym_to_canonical[syn.strip().lower()] = canonical

            for alias in entry.get("company_aliases", {}).values():
                self._synonym_to_canonical[alias.strip().lower()] = canonical

    def to_canonical(self, raw_label: str) -> str | None:
        """Direct lookup: raw PDF label → canonical key. None if not found."""
        return self._synonym_to_canonical.get(raw_label.strip().lower())

    def get_synonyms(self, label: str) -> list[str]:
        """Return all synonyms for a canonical or synonym label."""
        canonical = self.to_canonical(label) or (
            label if label in self._canonical_to_meta else None
        )
        if canonical is None:
            return []
        return self._canonical_to_meta[canonical].get("synonyms", [])

    def is_percentage(self, canonical: str) -> bool:
        """True if this metric's raw values are percentage strings needing /100."""
        return bool(self._canonical_to_meta.get(canonical, {}).get("is_percentage", False))

    def meta(self, canonical: str) -> dict:
        return self._canonical_to_meta.get(canonical, {})

    def all_canonicals(self) -> list[str]:
        return list(self._canonical_to_meta.keys())
