"""
utils/taxonomy.py - Taxonomy data model

The taxonomy is the skeleton of the survey, supporting:
- Multi-level tree structure (major categories/subcategories)
- Version control and changelog
- Serialization/deserialization (compatible with LangGraph state)
- Human-in-the-loop control (major category changes require confirmation)
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TaxonomyCategory:
    """
    A taxonomy node (major category or subcategory).

    Tree structure: parent_id=None indicates a root-level major category;
                   nodes with a parent_id are subcategories.
    """
    id: str                                    # Unique ID (UUID)
    name: str                                  # Category name
    description: str                           # Category description
    parent_id: str | None                      # Parent category ID (None = root major category)
    paper_ids: list[str] = field(default_factory=list)       # Papers belonging to this category
    subcategories: list["TaxonomyCategory"] = field(default_factory=list)  # Subcategory list

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict (recursive)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_id": self.parent_id,
            "paper_ids": self.paper_ids,
            "subcategories": [s.to_dict() for s in self.subcategories],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaxonomyCategory":
        """Restore from dict (recursive)."""
        subcategories = [
            cls.from_dict(s) for s in data.get("subcategories", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            parent_id=data.get("parent_id"),
            paper_ids=data.get("paper_ids", []),
            subcategories=subcategories,
        )


@dataclass
class Taxonomy:
    """
    Complete taxonomy, including version control and change history.

    Integration with LangGraph state:
    - to_dict() is used to store in state["taxonomy"]
    - from_dict() is used to restore from state
    """
    categories: list[TaxonomyCategory] = field(default_factory=list)  # Root major categories
    version: int = 0
    changelog: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to LangGraph state-compatible dict format."""
        return {
            "version": self.version,
            "categories": [c.to_dict() for c in self.categories],
            "changelog": self.changelog,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Taxonomy":
        """Restore taxonomy from LangGraph state dict."""
        categories = [
            TaxonomyCategory.from_dict(c) for c in data.get("categories", [])
        ]
        return cls(
            categories=categories,
            version=data.get("version", 0),
            changelog=data.get("changelog", []),
        )

    @classmethod
    def empty(cls) -> "Taxonomy":
        """Create an empty taxonomy."""
        return cls(categories=[], version=0, changelog=[])


# ──────────────────────────────────────────────────────────────────────────────
# Taxonomy operation utilities
# ──────────────────────────────────────────────────────────────────────────────

class TaxonomyManager:
    """
    Taxonomy change manager.

    Encapsulates all add/remove/modify operations on the taxonomy,
    automatically tracking change type (major/minor) for human-in-the-loop decisions.
    """

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    @property
    def taxonomy(self) -> Taxonomy:
        return self._taxonomy

    def add_major_category(self, name: str, description: str) -> TaxonomyCategory:
        """
        Add a root-level major category.

        Major change: requires human confirmation in BALANCED/STRICT mode.
        """
        cat = TaxonomyCategory(
            id=f"cat_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            parent_id=None,
        )
        self._taxonomy.categories.append(cat)
        self._taxonomy.version += 1
        self._taxonomy.changelog.append(
            f"v{self._taxonomy.version}: added major category '{name}'"
        )
        return cat

    def add_subcategory(
        self,
        parent_id: str,
        name: str,
        description: str,
    ) -> TaxonomyCategory | None:
        """
        Add a subcategory under the specified parent.

        Can be applied automatically in BALANCED mode, no human confirmation needed.
        Returns None if the parent does not exist.
        """
        parent = self._find_category(parent_id)
        if parent is None:
            return None

        subcat = TaxonomyCategory(
            id=f"cat_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            parent_id=parent_id,
        )
        parent.subcategories.append(subcat)
        self._taxonomy.version += 1
        self._taxonomy.changelog.append(
            f"v{self._taxonomy.version}: added subcategory '{name}' under '{parent.name}'"
        )
        return subcat

    def assign_paper(self, paper_id: str, category_id: str) -> bool:
        """Assign a paper to the specified category. Returns True on success."""
        cat = self._find_category(category_id)
        if cat is None:
            return False
        if paper_id not in cat.paper_ids:
            cat.paper_ids.append(paper_id)
        return True

    def remove_paper_from_category(self, paper_id: str, category_id: str) -> bool:
        """Remove a paper from a category."""
        cat = self._find_category(category_id)
        if cat is None:
            return False
        if paper_id in cat.paper_ids:
            cat.paper_ids.remove(paper_id)
        return True

    def rename_category(self, category_id: str, new_name: str) -> bool:
        """
        Rename a category.

        Major change: renaming a major category requires human confirmation (BALANCED/STRICT mode).
        """
        cat = self._find_category(category_id)
        if cat is None:
            return False
        old_name = cat.name
        cat.name = new_name
        self._taxonomy.version += 1
        is_major = cat.parent_id is None
        self._taxonomy.changelog.append(
            f"v{self._taxonomy.version}: {'major category' if is_major else 'subcategory'}"
            f" '{old_name}' renamed to '{new_name}'"
        )
        return True

    def get_all_categories_flat(self) -> list[TaxonomyCategory]:
        """Return all category nodes as a flat list (depth-first)."""
        result: list[TaxonomyCategory] = []

        def _dfs(cats: list[TaxonomyCategory]) -> None:
            for cat in cats:
                result.append(cat)
                _dfs(cat.subcategories)

        _dfs(self._taxonomy.categories)
        return result

    def is_major_category_change(self, change_type: str, category_id: str | None = None) -> bool:
        """
        Determine whether a change is a "major category change" (requiring human confirmation).

        Args:
            change_type: "add_major" | "add_sub" | "rename" | "delete" | "merge"
            category_id: Related category ID (used to determine level for rename)
        """
        if change_type in ("add_major", "merge", "delete"):
            return True
        if change_type == "rename" and category_id:
            cat = self._find_category(category_id)
            return cat is not None and cat.parent_id is None
        return False

    def _find_category(self, category_id: str) -> TaxonomyCategory | None:
        """Depth-first search to find a category node."""
        def _search(cats: list[TaxonomyCategory]) -> TaxonomyCategory | None:
            for cat in cats:
                if cat.id == category_id:
                    return cat
                found = _search(cat.subcategories)
                if found:
                    return found
            return None

        return _search(self._taxonomy.categories)

    def to_markdown_outline(self) -> str:
        """
        Render the taxonomy as a Markdown outline (for display to users).

        Example output:
        ## 1. Attention Mechanisms
        - **1.1 Self-Attention** (12 papers)
        - **1.2 Cross-Attention** (8 papers)
        ## 2. Efficient Transformers
        ...
        """
        lines: list[str] = []
        for i, major_cat in enumerate(self._taxonomy.categories, 1):
            paper_count = len(major_cat.paper_ids)
            lines.append(f"## {i}. {major_cat.name} ({paper_count} papers)")
            if major_cat.description:
                lines.append(f"   *{major_cat.description}*")
            for j, sub in enumerate(major_cat.subcategories, 1):
                sub_count = len(sub.paper_ids)
                lines.append(f"- **{i}.{j} {sub.name}** ({sub_count} papers)")
            lines.append("")
        return "\n".join(lines)
