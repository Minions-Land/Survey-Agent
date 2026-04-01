<div align="center">

# Survey Agent

**Fully Automated Academic Literature Survey System Powered by Multi-Agent Collaboration**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF6B35)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Code Style](https://img.shields.io/badge/Code%20Style-Ruff-purple)](https://docs.astral.sh/ruff/)

[中文](README.md) · [Quick Start](#quick-start) · [Web Interface Guide](WEB_GUIDE.md) · [Configuration](#configuration) · [Supported Models](#supported-models)

</div>

---

Survey Agent is an end-to-end academic survey automation pipeline. It understands a researcher's prior knowledge through multi-turn dialogue, automatically retrieves, classifies, and analyzes papers, and ultimately produces an academic-grade survey document with strict citation validation. The system employs a **heterogeneous LLM collaboration** strategy — lightweight models handle batch extraction while high-quality models handle dialogue and writing — balancing output quality with API cost.

## Features

### Prior Knowledge Dialogue
Conducts structured multi-turn conversation at startup to extract research background, known prior work, expected findings, and unique angles, ensuring the final survey genuinely reflects the researcher's perspective. Supports uploading a **start document** (preliminary notes, planning files, Word/PDF/Markdown) — the agent reads it first and asks targeted follow-up questions instead of starting from scratch.

### Multi-Format Reference Materials
Seed papers can be provided in multiple ways:
- **Direct ID input**: Semantic Scholar ID / arXiv ID / DOI, comma-separated
- **Title search**: Search online by keywords and check boxes to select
- **PDF upload**: Upload a paper PDF directly; the system auto-identifies and adds it to the seed set
- **Start document**: A PDF / Markdown / Word / TXT research planning file

### Duplicate Survey Detection
Before beginning research, automatically searches for existing surveys in the field and evaluates overlap. If a highly similar existing work is found, presents a summary and asks whether to continue (optionally with a differentiated angle).

### Bidirectional Paper Network Expansion with Relevance Filtering
- **Backward expansion**: Starting from seed papers, recursively traces reference chains
- **Forward expansion**: Discovers newer work that cites the papers under study
- Built-in **topic keyword filter**: automatically discards off-topic citations during expansion, preventing cross-domain drift
- Multi-source search across Semantic Scholar, arXiv, and OpenReview with automatic deduplication

### Taxonomy Visualization (Interactive Drawer Panel)
The web interface provides a bottom slide-up taxonomy visualization drawer that updates in real time:
- **Horizontal tree view**: Hierarchical category structure with SVG connector lines
- **Confidence threshold slider**: Drag to set the classification threshold, with visual danger-zone warnings and a two-step confirmation flow
- **Edit mode**: Drag-and-drop to reorganize categories, rename nodes, then apply or cancel all at once
- **Paper count limit control**: Dynamically adjust the maximum paper count during a live run (can be raised, not lowered below the current classified count)

### Dynamic Taxonomy with Human Confirmation
The system maintains a classification scheme that evolves as research progresses, supporting three intervention sensitivity levels:
- **Strict**: All taxonomy changes require confirmation
- **Balanced** (recommended): Major category changes require confirmation; minor changes execute automatically
- **Liberal**: Fully automatic — no confirmation required

### Reference Downloader
Standalone tool module: upload any PDF, and the system automatically extracts its reference list and bulk-downloads available full-text PDFs from arXiv / Unpaywall.

### Local PDF Management
Supports local paper storage with **page-level read tracking** — each PDF page is read by the LLM only once, preventing duplicate token consumption. Drop PDFs into the `unclassified/` directory at any time (optionally with a companion `.bib` file); the system auto-detects and classifies them.

### Anti-Hallucination Writing Engine
- Maintains a BibTeX registry; all citations are sourced from API-verified real papers
- Injects the complete cite-key list into writing prompts; validates `\cite{}` legality post-writing
- Automatically triggers a rewrite flow when invalid citations are detected
- Supports both **LaTeX** (default) and **Markdown** output formats

### Full-Featured Web Interface
- Chat bubble UI — agent messages on the left, user messages on the right
- 7-stage pipeline progress visualization (Dialogue → Search → Research → Extraction → Taxonomy → Writing → Complete)
- Chinese / English language toggle
- Light / dark theme toggle

---

## Quick Start

### Prerequisites

- Python 3.11+
- At least one supported LLM API key (see [Supported Models](#supported-models))

### Installation

**Recommended: use a conda virtual environment (especially on Apple Silicon)**

```bash
# 1. Create and activate conda environment
conda create -n survey-agent python=3.11 -y
conda activate survey-agent

# 2. Clone the project
git clone https://github.com/your-username/survey-agent.git
cd survey-agent

# 3. Full install (recommended)
pip install -e ".[web,openai-compat,pdf]"
```

### Configure API Key

```bash
cp .env.example .env
```

Edit `.env` and fill in at least one LLM provider key:

```dotenv
# Use Claude (recommended)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx

# Or use another model (pick one)
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AIza...
# DEEPSEEK_API_KEY=sk-...
```

### Run

```bash
# Web interface mode (recommended)
survey-agent --web
# Open http://localhost:8080 in your browser

# Interactive terminal mode
survey-agent

# Start with a specified topic
survey-agent --topic "Survey of Vision Transformers"
```

> **Web interface walkthrough** → see [WEB_GUIDE.md](WEB_GUIDE.md)

---

## Architecture

```
Input: topic + reference materials (IDs / PDFs / start doc) + local PDF dir (optional)
                              │
              ┌───────────────┴───────────────┐
              ▼
    preprocess_materials         (extract knowledge from start document)
              │
              ▼
    ┌─────────────────┐
    │  Dialogue Agent  │  ←─ multi-turn dialogue, extract prior knowledge
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │  Survey Search  │  ←─ detect duplicate surveys
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │ Research Agent  │  ←─ bidirectional expansion + topic filtering
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │Extraction Agent │  ←─ structured extraction
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │ Taxonomy Agent  │  ←─ taxonomy construction (with human review)
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │  Writer Agent   │  ←─ anti-hallucination writing
    └────────┬────────┘
             ▼
    Output: survey.tex / survey.md + references.bib + mindmap
```

**Human-in-the-loop checkpoints** (LangGraph `interrupt()`):
1. Dialogue phase — waits for user reply each turn
2. Duplicate survey found — asks whether to continue
3. Taxonomy major category change — awaits review (Balanced/Strict mode)
4. After outline generation — confirm or request revisions

---

## Supported Models

The system uses a **dual-model** strategy: a **lightweight model** for batch text extraction and a **high-quality model** for dialogue and writing.

| Provider | Lightweight Model | High-Quality Model | Environment Variable |
|----------|-------------------|--------------------|----------------------|
| **Anthropic** (recommended) | claude-haiku-4-5 | claude-opus-4-6 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o-mini | gpt-4o | `OPENAI_API_KEY` |
| Google Gemini | gemini-2.0-flash-lite | gemini-2.5-pro | `GEMINI_API_KEY` |
| DeepSeek | deepseek-chat | deepseek-reasoner | `DEEPSEEK_API_KEY` |
| Kimi (Moonshot) | moonshot-v1-8k | moonshot-v1-128k | `MOONSHOT_API_KEY` |
| Qwen | qwen-turbo | qwen-max | `DASHSCOPE_API_KEY` |
| GLM (Zhipu AI) | glm-4-flash | glm-4-plus | `ZHIPUAI_API_KEY` |

Specify model names via `CHEAP_MODEL` and `EXPENSIVE_MODEL` in `.env`, or switch them live in the web interface.

---

## Supported Search Sources

| Source | Characteristics | API Key |
|--------|-----------------|---------|
| **Semantic Scholar** | Most comprehensive; includes citation network and influence scores | Optional (rate-limited without key) |
| **arXiv** | Latest preprints; free and unlimited | Not required |
| **OpenReview** | Top-venue papers (NeurIPS/ICLR etc.) with reviewer versions | Not required |

Multi-source search auto-deduplicates and merges results, using Semantic Scholar citation data as the primary source for network expansion.

---

## Project Structure

```
survey-agent/
├── src/survey_agent/
│   ├── agents/              # Five core agents
│   │   ├── dialogue_agent.py      # Dialogue & prior knowledge extraction
│   │   ├── retrieval_agent.py     # Literature retrieval & network expansion
│   │   ├── extraction_agent.py    # Structured information extraction
│   │   ├── taxonomy_agent.py      # Taxonomy management
│   │   └── writer_agent.py        # Survey writing & LaTeX output
│   ├── providers/           # Injectable provider implementations
│   │   ├── anthropic_llm.py       # Claude (with adaptive thinking)
│   │   ├── openai_compatible.py   # GPT/Gemini/DeepSeek etc.
│   │   ├── semantic_scholar.py    # Semantic Scholar API
│   │   ├── arxiv_search.py        # arXiv API
│   │   └── composite_search.py    # Multi-source search aggregator
│   ├── interfaces/          # Abstract base classes (DI interfaces)
│   ├── utils/               # Utilities
│   │   ├── paper_card.py          # Paper data structure
│   │   ├── bib_manager.py         # BibTeX management & anti-hallucination validation
│   │   ├── taxonomy.py            # Taxonomy data structure
│   │   ├── paper_storage.py       # Local PDF storage & read tracking
│   │   └── document_reader.py     # Start document reader (PDF/MD/Word/TXT)
│   ├── workflow/
│   │   ├── nodes.py               # LangGraph node functions
│   │   └── graph.py               # StateGraph assembly
│   └── state.py             # Global state TypedDict
├── web/                     # Web interface
│   ├── app.py                     # FastAPI + WebSocket server
│   ├── runner.py                  # LangGraph ↔ WebSocket bridge
│   └── static/
│       ├── index.html             # Main page
│       ├── app.js                 # Frontend logic (chat, pipeline, uploads)
│       ├── style.css              # Main styles
│       ├── taxonomy_viz.js        # Taxonomy visualization component
│       └── taxonomy_viz.css       # Taxonomy visualization styles
├── prompts/                 # Editable LLM prompt templates
│   ├── dialogue_initial.md
│   ├── extraction_card.md
│   ├── taxonomy_suggest.md
│   └── writer_section.md
├── data/
│   ├── surveys/             # Generated survey files (auto-created)
│   └── papers/              # Local PDF storage (optional)
│       ├── unclassified/    # Drop new PDFs here for auto-classification
│       └── classified/      # Classified PDFs (auto-managed)
├── .env.example             # Configuration template
├── pyproject.toml
├── render.yaml              # Render.com one-click deploy config
├── Dockerfile
├── SETUP.md                 # Detailed configuration guide
└── WEB_GUIDE.md             # Web interface usage guide
```

---

## Configuration

All configuration is managed through the `.env` file. See [`.env.example`](.env.example) for the full template.

### Key Parameters

```dotenv
# LLM models (customize specific model names)
CHEAP_MODEL=claude-haiku-4-5         # For batch extraction
EXPENSIVE_MODEL=claude-opus-4-6      # For writing & dialogue

# Research scale
MAX_PAPERS_PER_EXPANSION=20          # Max papers per expansion round
MAX_TOTAL_PAPERS=200                 # Total paper limit (adjustable live in web UI)

# Taxonomy sensitivity
TAXONOMY_UPDATE_SENSITIVITY=balanced # strict | balanced | liberal

# Output format
OUTPUT_FORMAT=latex                  # latex | markdown

# Local PDF directory
LOCAL_PAPERS_DIR=data/papers         # Leave empty to skip local PDF processing

# Literature search
SEMANTIC_SCHOLAR_API_KEY=            # Optional; rate-limited without key
```

### CLI Arguments

```bash
survey-agent --help

Options:
  --topic TEXT              Survey topic (prompts interactively if omitted)
  --seeds TEXT              Comma-separated seed paper IDs (S2/arXiv/DOI)
  --sensitivity CHOICE      strict | balanced | liberal  [default: balanced]
  --output-format CHOICE    latex | markdown  [default: latex]
  --mindmap                 Generate a Mermaid mind map
  --papers-dir TEXT         Local PDF storage directory
  --max-papers INT          Total paper count limit  [default: 200]
  --web                     Launch web interface
  --web-port INT            Web interface port  [default: 8080]
```

---

## Web Interface

```bash
survey-agent --web
# Open http://localhost:8080 in your browser
```

Web interface highlights:
- **Chat bubble UI**: agent and user messages side by side, clearly distinguished
- **Pipeline stage visualization**: 7 stages highlighted in real time with a sub-status bar
- **Taxonomy visualization drawer**: bottom pull-up panel with live horizontal tree updates
- **Reference materials panel**: ID input / title search / PDF upload all in one
- **Start document upload**: import an existing planning doc to reduce repetitive explanation
- **Reference downloader tool**: upload a PDF to bulk-fetch its cited papers

For a full walkthrough, see [WEB_GUIDE.md](WEB_GUIDE.md).

### Deploy to the Cloud

**Render.com** (free tier): Push the code to GitHub, create a new Web Service on [render.com](https://render.com), and link the repository. The platform auto-detects [`render.yaml`](render.yaml) for configuration. Set your `ANTHROPIC_API_KEY` and other secrets in the Dashboard environment variables.

**Docker**:

```bash
docker build -t survey-agent .
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-xxxxxx \
  survey-agent
```

---

## Output Files

Survey Agent generates the following files in `data/surveys/` upon completion:

| File | Description |
|------|-------------|
| `survey_<topic>_<timestamp>.tex` | Full LaTeX survey (with `\cite{}` citations) |
| `survey_<topic>_<timestamp>.md` | Markdown format survey |
| `survey_<topic>_<timestamp>.bib` | BibTeX reference library |
| `mindmap_<topic>_<timestamp>.md` | Mermaid mind map (when enabled) |

The LaTeX file works directly with the `.bib` file — run `pdflatex` + `bibtex` to compile to PDF.

---

## Optional Feature Installation

```bash
# Semantic vector clustering (improves taxonomy accuracy)
pip install -e ".[clustering]"
# Apple Silicon users also need: brew install libomp

# Local PDF text extraction
pip install -e ".[pdf]"

# Web interface
pip install -e ".[web]"

# Non-Claude LLMs (GPT/Gemini/DeepSeek etc.)
pip install -e ".[openai-compat]"

# Full install
pip install -e ".[web,openai-compat,pdf,clustering]"
```

---

## Custom Prompts

The Markdown files under `prompts/` are the system prompts for each agent and can be edited directly to adjust behavior:

| File | Purpose |
|------|---------|
| `dialogue_initial.md` | Dialogue style and turn control |
| `extraction_card.md` | Paper extraction fields and format |
| `taxonomy_suggest.md` | Taxonomy change suggestion criteria |
| `writer_section.md` | Writing style and citation conventions |

> **Note**: The `{cite_key_list}` placeholder in `writer_section.md` is automatically filled by the program. **Do not remove it.**

---

## Roadmap

- [x] Multi-turn prior knowledge dialogue
- [x] Start document upload and knowledge extraction
- [x] Multi-format reference materials (ID / title search / PDF upload)
- [x] Duplicate survey detection and evaluation
- [x] Bidirectional paper network expansion + topic relevance filtering
- [x] Dynamic taxonomy with human confirmation (three sensitivity levels)
- [x] Taxonomy visualization drawer (interactive tree + threshold slider + edit mode)
- [x] LaTeX / Markdown output
- [x] Anti-hallucination BibTeX validation
- [x] Multi-LLM provider support (7 providers)
- [x] Web interface (chat bubbles + pipeline visualization)
- [x] Local PDF management (page-level read tracking)
- [x] Reference bulk-download tool
- [x] Mermaid mind map generation
- [ ] Persistent checkpointing (resume from interruption)
- [ ] Paper translation and bilingual comparison
- [ ] Full OpenReview integration
- [ ] Figure and experiment result extraction
- [ ] Zotero / Mendeley integration

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add: your feature description'`
4. Push the branch: `git push origin feature/your-feature`
5. Open a Pull Request

**Code style**: This project uses `ruff` for formatting. Before submitting, run:

```bash
pip install -e ".[dev]"
ruff check src/ && ruff format src/
```

---

## License

This project is open-source under the [MIT License](LICENSE).

---

<div align="center">

If this project is useful to you, a Star is appreciated!

</div>
