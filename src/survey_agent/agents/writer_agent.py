"""
agents/writer_agent.py - Survey writing Agent

Responsibilities:
1. Generate survey outline (based on taxonomy + paper notes)
2. Write survey sections chapter by chapter (using expensive_model + streaming)
3. Strictly prevent hallucinated citations (only use cite_keys registered in BibManager)
4. Validate all citations after writing

Core anti-hallucination mechanism:
- Writing prompt includes the full list of available citations
- Use BibManager.validate_citations() for post-writing validation
- Automatically rewrite when invalid citations are found
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from survey_agent.interfaces.llm import LLMProvider
from survey_agent.utils.bib_manager import BibManager
from survey_agent.utils.taxonomy import Taxonomy, TaxonomyManager

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


class WriterAgent:
    """
    Academic survey writing Agent.

    Uses expensive_model (Opus) with streaming for writing,
    providing real-time output experience.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        self._writer_prompt = self._load_prompt("writer_section.md")

    def _load_prompt(self, filename: str) -> str:
        path = _PROMPT_DIR / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    async def generate_outline(
        self,
        topic: str,
        taxonomy: Taxonomy,
        paper_notes: dict[str, str],
        prior_knowledge: dict[str, Any],
        user_angle: str,
    ) -> list[dict[str, Any]]:
        """
        Generate survey outline based on taxonomy and paper notes.

        Args:
            topic: Survey topic
            taxonomy: Final taxonomy
            paper_notes: {paper_id: note_markdown} dict
            prior_knowledge: User's prior knowledge
            user_angle: User's unique angle

        Returns:
            Outline list, each item being:
            {
                "section_id": "sec_01",
                "title": "Section title",
                "description": "This section will cover...",
                "paper_ids": ["s2_id_1", ...],
                "order": 1
            }
        """
        manager = TaxonomyManager(taxonomy)
        taxonomy_outline = manager.to_markdown_outline()

        research_questions = "\n".join(
            f"- {rq}" for rq in prior_knowledge.get("research_questions", [])
        )
        new_findings = "\n".join(prior_knowledge.get("new_findings", []))

        prompt = f"""Survey topic: {topic}
User's unique angle: {user_angle or "No specific angle"}

Research questions:
{research_questions or "Not specified"}

Key findings from literature:
{new_findings or "None"}

Current taxonomy:
{taxonomy_outline}

Please generate a complete survey outline. Output a JSON array:
[
  {{
    "section_id": "sec_01",
    "title": "Section title",
    "description": "This section will introduce...",
    "paper_ids": [],
    "order": 1
  }},
  ...
]

Outline requirements:
1. Include Introduction and Conclusion sections
2. Main sections organized according to taxonomy
3. Reflect the user's unique angle
4. section_id format: sec_01, sec_02, ...

Output only the JSON array, no other text.
"""
        response = await self._llm.expensive_complete(
            [{"role": "user", "content": prompt}],
            max_tokens=3000,
        )

        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                outline = json.loads(response[start:end])
                return outline
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Outline parsing failed: {e}")

        # Fallback: generate simple outline based on taxonomy
        return _fallback_outline(taxonomy)

    async def write_section(
        self,
        section: dict[str, Any],
        topic: str,
        paper_notes: dict[str, str],
        bib_manager: BibManager,
        prior_knowledge: dict[str, Any],
        full_outline: list[dict[str, Any]],
    ) -> str:
        """
        Write a single section (with streaming output).

        Anti-hallucination mechanism:
        1. Prompt includes the full list of available citations
        2. Call validate_citations() after writing
        3. Prompt rewrite when invalid citations are found

        Args:
            section: Section definition (from generate_outline)
            topic: Survey topic
            paper_notes: All paper notes dict
            bib_manager: BibTeX manager (anti-hallucination)
            prior_knowledge: User's prior knowledge
            full_outline: Full outline (gives LLM context)

        Returns:
            Section content (Markdown + LaTeX \\cite{} format)
        """
        # Get paper notes relevant to this section
        section_paper_ids = section.get("paper_ids", [])
        relevant_notes = "\n\n".join(
            paper_notes.get(pid, "") for pid in section_paper_ids
            if pid in paper_notes
        )

        # If no specific papers, use a sample of all paper notes
        if not relevant_notes and paper_notes:
            relevant_notes = "\n\n".join(list(paper_notes.values())[:15])

        # Full list of available citations (core of anti-hallucination)
        cite_key_list = bib_manager.get_cite_key_summary()

        system = (self._writer_prompt or _DEFAULT_WRITER_SYSTEM).format(
            cite_key_list=cite_key_list
        )

        outline_str = "\n".join(
            f"{s['order']}. {s['title']}" for s in full_outline
        )

        messages = [
            {
                "role": "user",
                "content": f"""Survey topic: {topic}
Current section: {section['title']} ({section['description']})

Full outline (for context):
{outline_str}

Relevant paper notes for this section:
{relevant_notes or "No specific papers; please write synthesized content based on the available citations list"}

Requirements:
1. Use \\cite{{cite_key}} format for citations (only use cite_keys from the list above)
2. Academic writing style, in English
3. Do not add a section heading (managed by the external framework)
4. Approximately 500-1000 words

Please write the content of this section:
""",
            }
        ]

        # Streaming writing (display to user in real time)
        print(f"\n Writing section: \"{section['title']}\"...\n")
        result: list[str] = []
        async for token in self._llm.expensive_stream(
            messages, system=system, max_tokens=4096
        ):
            result.append(token)
            print(token, end="", flush=True)
        print("\n")

        draft = "".join(result)

        # Validate citation validity
        is_valid, invalid_keys = bib_manager.validate_citations(draft)
        if not is_valid:
            logger.warning(f"Section {section['section_id']} contains invalid citations: {invalid_keys}")
            draft = await self._fix_invalid_citations(
                draft, invalid_keys, bib_manager, section["title"]
            )

        return draft

    async def assemble_survey(
        self,
        outline: list[dict[str, Any]],
        sections: dict[str, str],
        topic: str,
        prior_knowledge: dict[str, Any],
        output_format: str = "markdown",
    ) -> str:
        """
        Assemble all sections into a complete survey document.

        Args:
            outline: Outline list
            sections: {section_id: content} dict
            topic: Survey topic
            prior_knowledge: User's prior knowledge (used for generating abstract)
            output_format: "markdown" (default) or "latex"

        Returns:
            Complete survey text (Markdown or LaTeX)
        """
        if output_format == "latex":
            return self._assemble_latex(outline, sections, topic)
        return self._assemble_markdown(outline, sections, topic)

    def _assemble_markdown(
        self,
        outline: list[dict[str, Any]],
        sections: dict[str, str],
        topic: str,
    ) -> str:
        """Assemble Markdown-format survey."""
        lines = [f"# {topic}", "", "---", ""]
        sorted_outline = sorted(outline, key=lambda s: s.get("order", 99))
        for section in sorted_outline:
            sid = section["section_id"]
            content = sections.get(sid, "_This section has not been generated yet_")
            lines.append(f"## {section['order']}. {section['title']}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def _assemble_latex(
        self,
        outline: list[dict[str, Any]],
        sections: dict[str, str],
        topic: str,
    ) -> str:
        """
        Assemble LaTeX-format survey.

        Generates a complete .tex file with \\documentclass, \\begin{document},
        section structure, and \\bibliography command.
        \\cite{} citation format is already correct from the writing stage, no conversion needed.
        """
        import re as _re

        def _escape(text: str) -> str:
            """Escape LaTeX special characters (but not \\cite{})."""
            for char, replacement in [
                ("&", "\\&"), ("%", "\\%"), ("$", "\\$"),
                ("#", "\\#"), ("_", "\\_"), ("^", "\\^{}"),
                ("{", "\\{"), ("}", "\\}"),
            ]:
                # Avoid escaping braces inside \cite{...} and \\
                text = _re.sub(
                    r"(?<!\\)" + _re.escape(char),
                    replacement,
                    text,
                )
            return text

        def _md_to_latex(text: str) -> str:
            """Simple Markdown → LaTeX conversion (bold, italic, lists)."""
            # **bold** → \textbf{bold}
            text = _re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
            # *italic* → \textit{italic}
            text = _re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
            # - item → \item
            text = _re.sub(r"^- (.+)$", r"\\item \1", text, flags=_re.MULTILINE)
            return text

        safe_topic = _escape(topic)
        sorted_outline = sorted(outline, key=lambda s: s.get("order", 99))

        lines = [
            "\\documentclass[12pt,a4paper]{article}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage{hyperref}",
            "\\usepackage{natbib}",
            "\\usepackage{amsmath}",
            "\\usepackage[margin=2.5cm]{geometry}",
            "",
            f"\\title{{{safe_topic}}}",
            "\\date{\\today}",
            "",
            "\\begin{document}",
            "\\maketitle",
            "\\tableofcontents",
            "\\newpage",
            "",
        ]

        for section in sorted_outline:
            sid = section["section_id"]
            title = _escape(section["title"])
            content = sections.get(sid, "This section has not been generated yet.")
            content = _md_to_latex(content)
            lines.append(f"\\section{{{title}}}")
            lines.append("")
            lines.append(content)
            lines.append("")

        lines += [
            "\\bibliographystyle{plainnat}",
            "\\bibliography{references}",
            "",
            "\\end{document}",
        ]

        return "\n".join(lines)

    async def generate_mindmap(
        self,
        topic: str,
        taxonomy: Any,
        outline: list[dict[str, Any]],
    ) -> dict[str, str]:
        """
        Generate a research topic mind map.

        Returns two formats:
        1. Mermaid syntax (can be rendered directly in GitHub/Obsidian)
        2. AI image generation prompt (for text-to-image)

        Args:
            topic: Survey topic
            taxonomy: Taxonomy object or dict
            outline: Survey outline

        Returns:
            {"mermaid": "...", "image_prompt": "..."}
        """
        from survey_agent.utils.taxonomy import TaxonomyManager, Taxonomy

        if isinstance(taxonomy, dict):
            tax_obj = Taxonomy.from_dict(taxonomy)
        else:
            tax_obj = taxonomy

        manager = TaxonomyManager(tax_obj)
        cats = manager.get_all_categories_flat()

        # ── Generate Mermaid mind map ──────────────────────────────────────────
        mermaid_lines = ["mindmap", f"  root(({topic}))"]
        for cat in cats:
            if cat.parent_id is None:
                indent = "    "
                mermaid_lines.append(f"{indent}[{cat.name}]")
                for sub in cats:
                    if sub.parent_id == cat.id:
                        mermaid_lines.append(f"{indent}  ({sub.name})")

        # Add outline sections (if any)
        if outline:
            mermaid_lines.append("    [Survey Structure]")
            for sec in sorted(outline, key=lambda s: s.get("order", 99)):
                title = sec["title"][:30]
                mermaid_lines.append(f"      ({title})")

        mermaid_code = "\n".join(mermaid_lines)

        # ── Generate AI image prompt ──────────────────────────────────────────
        cat_names = [cat.name for cat in cats if cat.parent_id is None]
        sections = [s["title"] for s in outline[:6]] if outline else []

        image_prompt = f"""Create a detailed mind map visualization for an academic survey on "{topic}".

Central topic: {topic}

Main research categories (branches):
{chr(10).join(f"- {name}" for name in cat_names)}

Survey structure:
{chr(10).join(f"- {s}" for s in sections)}

Style requirements:
- Clean, academic style with hierarchical nodes
- Use different colors for each main branch
- Show connections between related concepts
- Include small paper/book icons for literature nodes
- Central node should be prominent and well-labeled
- Use a white or light gray background
- Font should be clear and readable (English labels)
- Overall size: wide landscape format, 1600x900px or similar

Make it look like a professional academic research map suitable for inclusion in a survey paper."""

        return {
            "mermaid": f"```mermaid\n{mermaid_code}\n```",
            "image_prompt": image_prompt,
        }

    async def _fix_invalid_citations(
        self,
        text: str,
        invalid_keys: list[str],
        bib_manager: BibManager,
        section_title: str,
    ) -> str:
        """Request LLM to rewrite and remove invalid citations when found."""
        valid_keys = bib_manager.get_all_cite_keys()
        prompt = f"""The following section ("{section_title}") contains invalid citation keys: {invalid_keys}

Valid citation keys (must only choose from these): {", ".join(valid_keys[:30])}

Please rewrite the text, removing all invalid citations (or replacing them with appropriate valid ones), keeping the content unchanged:

---
{text}
---

Output only the rewritten text, no other explanation.
"""
        fixed = await self._llm.expensive_complete(
            [{"role": "user", "content": prompt}],
            max_tokens=len(text.split()) * 3,
        )
        return fixed


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _fallback_outline(taxonomy: Taxonomy) -> list[dict[str, Any]]:
    """Generate a simple outline based on taxonomy (fallback when LLM parsing fails)."""
    outline: list[dict[str, Any]] = [
        {
            "section_id": "sec_01",
            "title": "Introduction",
            "description": "Research background, motivation, and survey structure",
            "paper_ids": [],
            "order": 1,
        }
    ]
    for i, cat in enumerate(taxonomy.categories, 2):
        outline.append({
            "section_id": f"sec_{i:02d}",
            "title": cat.name,
            "description": cat.description,
            "paper_ids": list(cat.paper_ids),
            "order": i,
        })
    outline.append({
        "section_id": f"sec_{len(outline) + 1:02d}",
        "title": "Conclusion and Future Directions",
        "description": "Research summary, open problems, and future directions",
        "paper_ids": [],
        "order": len(outline) + 1,
    })
    return outline


_DEFAULT_WRITER_SYSTEM = """\
You are a professional academic survey writing expert, skilled at writing high-quality, well-structured literature surveys.

Writing requirements:
1. Use \\cite{{cite_key}} format for citations
2. Strictly follow citation rules: {cite_key_list}
3. Academic writing style, content objective and accurate
4. Highlight connections, comparisons, and evolution between different works
5. Do not fabricate citations that do not exist
"""
