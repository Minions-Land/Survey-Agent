<div align="center">

# 📚 Survey Agent

**基于多智能体协作的全自动学术文献综述系统**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF6B35)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Code Style](https://img.shields.io/badge/Code%20Style-Ruff-purple)](https://docs.astral.sh/ruff/)

[English](README_EN.md) · [快速开始](#快速开始) · [网页界面教程](WEB_GUIDE.md) · [配置说明](#配置说明) · [支持的模型](#支持的模型)

</div>

---

Survey Agent 是一个端到端的学术综述自动化流水线。它通过多轮对话理解研究者的先验知识，自动检索、分类和分析文献，并最终生成带严格引用验证的学术级综述文档。系统采用**异构大模型协作**策略，将批量提取任务分配给轻量模型，将对话与写作任务分配给高质量模型，在保证质量的同时控制 API 成本。

## ✨ 核心特性

### 🗣️ 先验知识对话
启动时与用户进行多轮结构化对话，提取研究背景、已知工作、预期发现和独特切入角度，使最终综述真正反映研究者的视角。支持上传**起始文档**（初步规划、笔记、Word/PDF/Markdown），Agent 读取后会基于已有内容提问，而非重头询问。

### 📎 多形式参考材料
种子论文支持多种输入形式：
- **ID 直接输入**：Semantic Scholar ID / arXiv ID / DOI，逗号分隔
- **标题搜索**：输入关键词在线搜索并勾选
- **PDF 上传**：直接上传论文 PDF，系统自动识别并加入种子集
- **起始文档**：PDF / Markdown / Word / TXT 格式的研究规划文件

### 🔍 重复综述检测
在开展调研前，自动搜索领域内已有综述并评估相似度。如发现高度重叠的已有工作，向用户展示摘要并询问是否继续（可带差异化角度继续）。

### 🕸️ 双向论文网络扩展（主题相关性过滤）
- **向后扩展**：从种子论文出发，递归追溯参考文献
- **向前扩展**：通过引用关系发现引用上述论文的新工作
- 内置**主题关键词过滤器**：扩展时自动过滤与主题无关的引用，防止跨领域漂移
- 支持 Semantic Scholar、arXiv、OpenReview 多源搜索，自动去重合并

### 📊 分类法可视化（交互式抽屉面板）
网页版提供底部滑出的分类可视化抽屉，实时展示当前论文分类体系：
- **横向树状图**：层级分类结构 + SVG 连接线
- **置信度阈值调节**：自定义拖动滑块，带危险区视觉提示与二次确认
- **编辑模式**：拖拽重组分类，修改类别名称，一键应用或取消
- **论文上限控制**：运行时可动态调整最大论文数量（可随时调高，不可低于已分类数量）

### 🗂️ 动态分类法（含人工确认）
系统维护一套随调研进展持续演化的分类体系，支持三种人工介入敏感度：
- **Strict**：所有分类变更均需确认
- **Balanced**（推荐）：大类变更需确认，小类自动执行
- **Liberal**：全程自动，无需确认

### 📥 引用文献批量下载
独立工具模块：上传任意一篇 PDF，系统自动提取其参考文献列表，并从 arXiv / Unpaywall 批量下载可获取的全文 PDF。

### 📄 本地 PDF 管理
支持本地论文存储，配备**页面级读取追踪**——每页 PDF 只会被 LLM 读取一次，避免重复消耗 Token。可随时向 `unclassified/` 目录添加 PDF（可附配套 `.bib` 文件），系统自动检测并完成分类。

### ✍️ 防幻觉写作引擎
- 维护 BibTeX 注册表，所有引用均来自 API 验证的真实论文
- 写作时将完整引用键列表注入提示词，写作后执行 `\cite{}` 合法性验证
- 发现非法引用时自动触发重写流程
- 支持 **LaTeX**（默认）和 **Markdown** 两种输出格式

### 🌐 全功能网页界面
- 对话气泡式交互（Agent 左侧、用户右侧）
- 7 阶段流水线进度可视化（对话 → 搜索 → 研究 → 提取 → 分类 → 写作 → 完成）
- 中/英文双语界面切换
- 日间/夜间主题切换

---

## 🚀 快速开始

### 前置条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（推荐的包管理器）
- 至少一个支持的 LLM API Key（见[支持的模型](#支持的模型)）

### 安装

```bash
# 1. 安装 uv（如尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆项目
git clone https://github.com/your-username/survey-agent.git
cd survey-agent

# 3. 安装全功能版（推荐，uv 自动创建虚拟环境）
uv sync --all-extras
```

### 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，至少填写一个 LLM Provider 的密钥：

```dotenv
# 使用 Claude（推荐）
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx

# 或使用其他模型（任选一个）
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=AIza...
# DEEPSEEK_API_KEY=sk-...
```

### 启动

```bash
# 网页界面模式（推荐）
survey-agent --web
# 浏览器访问 http://localhost:8080

# 终端交互模式
survey-agent

# 指定主题直接启动
survey-agent --topic "视觉 Transformer 综述"
```

> **网页版使用教程** → 详见 [WEB_GUIDE.md](WEB_GUIDE.md)

---

## 🏗️ 系统架构

```
输入: 主题 + 参考材料（ID / PDF / 起始文档）+ 本地 PDF 目录（可选）
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    preprocess_materials              (首次跳过)
    （提取起始文档知识）
              │
              ▼
    ┌─────────────────┐
    │  Dialogue Agent  │  ←─ 多轮对话，提取先验知识
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │  Survey Search  │  ←─ 检测重复综述
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │ Research Agent  │  ←─ 双向网络扩展 + 主题过滤
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │Extraction Agent │  ←─ 结构化提取
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │ Taxonomy Agent  │  ←─ 分类法构建（含人工确认）
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │  Writer Agent   │  ←─ 防幻觉写作
    └────────┬────────┘
             ▼
    输出: survey.tex / survey.md + references.bib + mindmap
```

**人机交互检查点**（LangGraph `interrupt()`）：
1. 对话阶段 — 每轮等待用户回复
2. 重复综述发现 — 询问是否继续
3. 分类法大类变更 — 等待审核（Balanced/Strict 模式）
4. 大纲生成后 — 确认或提出修改意见

---

## 🤖 支持的模型

系统采用「双模型」策略：**轻量模型**用于批量文本提取，**高质量模型**用于对话与写作。

| Provider | 轻量模型 | 高质量模型 | 环境变量 |
|----------|----------|------------|----------|
| **Anthropic** (推荐) | claude-haiku-4-5 | claude-opus-4-6 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o-mini | gpt-4o | `OPENAI_API_KEY` |
| Google Gemini | gemini-2.0-flash-lite | gemini-2.5-pro | `GEMINI_API_KEY` |
| DeepSeek | deepseek-chat | deepseek-reasoner | `DEEPSEEK_API_KEY` |
| Kimi (Moonshot) | moonshot-v1-8k | moonshot-v1-128k | `MOONSHOT_API_KEY` |
| Qwen (通义千问) | qwen-turbo | qwen-max | `DASHSCOPE_API_KEY` |
| GLM (智谱 AI) | glm-4-flash | glm-4-plus | `ZHIPUAI_API_KEY` |

在 `.env` 中通过 `CHEAP_MODEL` 和 `EXPENSIVE_MODEL` 指定具体模型名称，或在网页界面中实时切换。

---

## 🔍 支持的搜索源

| 来源 | 特点 | API Key |
|------|------|---------|
| **Semantic Scholar** | 最全面，包含引用网络和影响力分数 | 可选（无 Key 时速率受限） |
| **arXiv** | 最新预印本，免费无限制 | 无需 |
| **OpenReview** | 顶会（NeurIPS/ICLR 等）审稿版本 | 无需 |

多源搜索自动去重合并，优先使用 Semantic Scholar 的引用关系数据进行网络扩展。

---

## 📂 项目结构

```
survey-agent/
├── src/survey_agent/
│   ├── agents/              # 五大核心 Agent
│   │   ├── dialogue_agent.py      # 对话 & 先验知识提取
│   │   ├── retrieval_agent.py     # 文献检索 & 网络扩展
│   │   ├── extraction_agent.py    # 结构化信息提取
│   │   ├── taxonomy_agent.py      # 分类法管理
│   │   └── writer_agent.py        # 综述写作 & LaTeX 输出
│   ├── providers/           # 可注入的 Provider 实现
│   │   ├── anthropic_llm.py       # Claude (含 adaptive thinking)
│   │   ├── openai_compatible.py   # GPT/Gemini/DeepSeek 等
│   │   ├── semantic_scholar.py    # Semantic Scholar API
│   │   ├── arxiv_search.py        # arXiv API
│   │   └── composite_search.py    # 多源搜索聚合
│   ├── interfaces/          # 抽象基类（依赖注入接口）
│   ├── utils/               # 工具类
│   │   ├── paper_card.py          # 论文数据结构
│   │   ├── bib_manager.py         # BibTeX 管理 & 防幻觉验证
│   │   ├── taxonomy.py            # 分类法数据结构
│   │   ├── paper_storage.py       # 本地 PDF 存储 & 读取追踪
│   │   └── document_reader.py     # 起始文档读取（PDF/MD/Word/TXT）
│   ├── workflow/
│   │   ├── nodes.py               # LangGraph 节点函数
│   │   └── graph.py               # StateGraph 组装
│   └── state.py             # 全局状态 TypedDict
├── web/                     # 网页界面
│   ├── app.py                     # FastAPI + WebSocket 服务端
│   ├── runner.py                  # LangGraph ↔ WebSocket 桥接
│   └── static/
│       ├── index.html             # 主页面
│       ├── app.js                 # 前端逻辑（对话、流水线、上传）
│       ├── style.css              # 主样式
│       ├── taxonomy_viz.js        # 分类可视化组件
│       └── taxonomy_viz.css       # 分类可视化样式
├── prompts/                 # 可编辑的 LLM Prompt 模板
│   ├── dialogue_initial.md
│   ├── extraction_card.md
│   ├── taxonomy_suggest.md
│   └── writer_section.md
├── data/
│   ├── surveys/             # 生成的综述文件（自动创建）
│   └── papers/              # 本地 PDF 存储（可选）
│       ├── unclassified/    # 待分类 PDF 放置目录
│       └── classified/      # 已分类 PDF（自动管理）
├── .env.example             # 配置模板
├── pyproject.toml
├── render.yaml              # Render.com 一键部署配置
├── Dockerfile
├── SETUP.md                 # 详细配置指南
└── WEB_GUIDE.md             # 网页版使用教程
```

---

## ⚙️ 配置说明

所有配置通过 `.env` 文件管理，完整模板见 [`.env.example`](.env.example)。

### 关键参数

```dotenv
# LLM 模型（可自定义具体模型名）
CHEAP_MODEL=claude-haiku-4-5         # 批量提取用
EXPENSIVE_MODEL=claude-opus-4-6      # 写作 & 对话用

# 调研规模
MAX_PAPERS_PER_EXPANSION=20          # 每轮扩展最大论文数
MAX_TOTAL_PAPERS=200                 # 调研总论文数上限（网页版可实时调整）

# 分类法敏感度
TAXONOMY_UPDATE_SENSITIVITY=balanced # strict | balanced | liberal

# 输出格式
OUTPUT_FORMAT=latex                  # latex | markdown

# 本地 PDF 目录
LOCAL_PAPERS_DIR=data/papers         # 留空则跳过本地 PDF 处理

# 文献搜索
SEMANTIC_SCHOLAR_API_KEY=            # 可选，无 Key 时速率受限
```

### 命令行参数

```bash
survey-agent --help

选项:
  --topic TEXT              综述主题（不提供则交互式输入）
  --seeds TEXT              逗号分隔的种子论文 ID（S2/arXiv/DOI）
  --sensitivity CHOICE      strict | balanced | liberal  [默认: balanced]
  --output-format CHOICE    latex | markdown  [默认: latex]
  --mindmap                 生成 Mermaid 思维导图
  --papers-dir TEXT         本地 PDF 存储目录
  --max-papers INT          论文总数上限  [默认: 200]
  --web                     启动网页界面
  --web-port INT            网页界面端口  [默认: 8080]
```

---

## 🌐 网页界面

```bash
survey-agent --web
# 浏览器访问 http://localhost:8080
```

网页版功能亮点：
- **对话气泡式 UI**：Agent 和用户消息分列左右，清晰区分
- **流水线阶段可视化**：7 个阶段实时高亮，顶部显示当前子状态
- **分类可视化抽屉**：底部上拉展开，横向树状图实时更新
- **参考材料管理**：ID 输入 / 标题搜索 / PDF 上传三合一
- **起始文档上传**：导入已有规划文档，减少重复说明
- **引用文献下载工具**：上传 PDF 即可批量抓取参考文献原文

详细使用说明见 [WEB_GUIDE.md](WEB_GUIDE.md)。

### 部署到云端

**Render.com**（免费套餐）：将代码推送到 GitHub，在 [render.com](https://render.com) 新建 Web Service 并关联仓库，系统自动识别 [`render.yaml`](render.yaml) 完成配置。需要在 Dashboard 中手动设置 `ANTHROPIC_API_KEY` 等环境变量。

**Docker**：

```bash
docker build -t survey-agent .
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=sk-ant-xxxxxx \
  survey-agent
```

---

## 📤 输出说明

Survey Agent 完成后在 `data/surveys/` 生成以下文件：

| 文件 | 说明 |
|------|------|
| `survey_<主题>_<时间戳>.tex` | 完整 LaTeX 综述（含 `\cite{}` 引用） |
| `survey_<主题>_<时间戳>.md` | Markdown 格式综述 |
| `survey_<主题>_<时间戳>.bib` | BibTeX 参考文献库 |
| `mindmap_<主题>_<时间戳>.md` | Mermaid 思维导图（启用时） |

LaTeX 文件可与 `.bib` 文件直接配合使用，运行 `pdflatex` + `bibtex` 即可编译为 PDF。

---

## 🔧 可选功能安装

```bash
# 语义向量聚类（提升分类准确性）
uv sync --extra clustering
# Apple Silicon 用户需额外安装: brew install libomp

# 本地 PDF 文本提取
uv sync --extra pdf

# 网页界面
uv sync --extra web

# 非 Claude LLM（GPT/Gemini/DeepSeek 等）
uv sync --extra openai-compat

# 全功能
uv sync --all-extras
```

---

## 📝 自定义 Prompt

`prompts/` 目录下的 Markdown 文件是各 Agent 的系统提示词，可直接编辑以调整行为：

| 文件 | 作用 |
|------|------|
| `dialogue_initial.md` | 对话风格与轮次控制 |
| `extraction_card.md` | 论文信息提取字段与格式 |
| `taxonomy_suggest.md` | 分类法变更建议标准 |
| `writer_section.md` | 写作风格与引用规范 |

> **注意**：`writer_section.md` 中的 `{cite_key_list}` 占位符由程序自动填充，**请勿删除**。

---

## 🗺️ 开发路线图

- [x] 多轮先验知识对话
- [x] 起始文档上传与知识提取
- [x] 多形式参考材料（ID / 标题搜索 / PDF 上传）
- [x] 重复综述检测与评估
- [x] 双向论文网络扩展 + 主题相关性过滤
- [x] 动态分类法（人工确认，三种敏感度）
- [x] 分类可视化抽屉（交互式树状图 + 阈值调节 + 编辑模式）
- [x] LaTeX / Markdown 输出
- [x] 防幻觉 BibTeX 验证
- [x] 多 LLM Provider 支持（7 家）
- [x] 网页界面（对话气泡 + 流水线可视化）
- [x] 本地 PDF 管理（页级读取追踪）
- [x] 引用文献批量���载工具
- [x] Mermaid 思维导图
- [ ] 持久化 Checkpoint（断点续传）
- [ ] 论文翻译与双语对照
- [ ] OpenReview 完整集成
- [ ] 图表与实验结果提取
- [ ] 与 Zotero / Mendeley 集成

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出功能建议！

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add: your feature description'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

**代码规范**：本项目使用 `ruff` 进行代码格式化，提交前请运行：

```bash
uv sync  # dev 依赖默认安装
uv run ruff check src/ && uv run ruff format src/
```

---

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。

---

<div align="center">

如果这个项目对你有帮助，欢迎 ⭐ Star！

</div>
