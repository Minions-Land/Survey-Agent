# Survey Agent - 配置指南

本文档列出了运行 Survey Agent 前需要手动完成的配置步骤。

---

## 1. Python 环境要求

- **Python 3.11+**（必须）
- [uv](https://docs.astral.sh/uv/)（推荐的包管理器，自动管理虚拟环境）

```bash
# 安装 uv（如尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

python --version   # 应显示 3.11.x 或更高
```

---

## 2. 安装依赖

### 基础安装（必选）

```bash
cd survey-agent
uv sync
```

### 可选：语义聚类功能

安装后，分类法构建可利用向量聚类（更准确的自动分类）：

```bash
uv sync --extra clustering
```

### 全功能安装

```bash
uv sync --all-extras
```

> **注意**：`hdbscan` 在 Apple Silicon 上需要 `brew install libomp` 才能正常编译。

---

## 3. 必须配置的 API Key

### 3.1 Anthropic API Key（必须）

Survey Agent 使用 Claude 进行对话、提取和写作。

1. 访问 [https://console.anthropic.com/](https://console.anthropic.com/) 获取 API Key
2. 复制 `.env.example` 为 `.env`：
   ```bash
   cp .env.example .env
   ```
3. 编辑 `.env`，填入你的 API Key：
   ```
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx
   ```

> **费用说明**：
> - 对话/提取使用 `claude-haiku-4-5`（廉价模型）
> - 写作使用 `claude-opus-4-6`（高质量模型，费用较高）
> - 处理 100 篇论文 + 写作约消耗 $2-5 USD

---

## 4. 可选配置

### 4.1 Semantic Scholar API Key（强烈推荐）

不使用 API Key 时，请求速率限制为每秒约 1 次（很慢）。
注册免费 API Key 后可大幅提升速度。

1. 访问 [https://www.semanticscholar.org/product/api](https://www.semanticscholar.org/product/api) 申请
2. 在 `.env` 中填入：
   ```
   SEMANTIC_SCHOLAR_API_KEY=your_key_here
   ```

### 4.2 模型选择

在 `.env` 中可自定义使用的模型：

```dotenv
# 批量提取用（建议保持 Haiku，节省成本）
CHEAP_MODEL=claude-haiku-4-5

# 写作/对话用（可改为 Sonnet 4.6 节省费用）
EXPENSIVE_MODEL=claude-opus-4-6
```

### 4.3 分类法更新敏感度

控制分类法变更时人工确认的频率：

```dotenv
# strict   - 所有变更均需人工确认（最安全）
# balanced - 仅大类变更需确认（默认，推荐）
# liberal  - 全部自动执行（最快）
TAXONOMY_UPDATE_SENSITIVITY=balanced
```

### 4.4 调研规模限制

```dotenv
# 每轮扩展最多检索的新论文数
MAX_PAPERS_PER_EXPANSION=20

# 整个调研过程的论文总上限
MAX_TOTAL_PAPERS=200
```

---

## 5. 目录结构说明

```
Survey Agent/
├── .env                    ← 你的私有配置（不要提交到 git）
├── .env.example            ← 配置模板
├── pyproject.toml          ← 项目依赖
├── prompts/                ← LLM Prompt 模板（可自定义）
│   ├── dialogue_initial.md ← 对话系统提示词
│   ├── extraction_card.md  ← 论文提取提示词
│   ├── taxonomy_suggest.md ← 分类建议提示词
│   └── writer_section.md   ← 写作提示词
├── data/
│   └── surveys/            ← 输出目录（自动创建）
│       └── survey_主题_时间戳.md
└── src/survey_agent/       ← 源代码
```

---

## 6. 快速启动

```bash
# 交互式启动（推荐初次使用）
survey-agent

# 直接指定主题
survey-agent --topic "视觉 Transformer 综述"

# 指定种子论文（Semantic Scholar Paper ID）
survey-agent --topic "注意力机制" --seeds "204e3073870fae3d05bcbc2f6a8e263d612023ed"

# 查看所有选项
survey-agent --help
```

### 如何获取 Semantic Scholar Paper ID？

在 [https://www.semanticscholar.org/](https://www.semanticscholar.org/) 搜索论文，
论文页面 URL 中的最后一段哈希值即为 Paper ID。

例如 `https://www.semanticscholar.org/paper/.../204e3073870fae3d05bcbc2f6a8e263d612023ed`
→ ID 为 `204e3073870fae3d05bcbc2f6a8e263d612023ed`

---

## 7. 输出文件说明

Survey Agent 完成后会在 `data/surveys/` 目录生成两个文件：

| 文件 | 说明 |
|------|------|
| `survey_<主题>_<时间戳>.md` | 完整综述（Markdown 格式） |
| `survey_<主题>_<时间戳>.bib` | BibTeX 参考文献库 |

Markdown 文件使用 `\cite{key}` 格式标注引用，配合 `.bib` 文件可直接导入 LaTeX 项目。

---

## 8. 常见问题

### Q: 运行时报 `ModuleNotFoundError: No module named 'survey_agent'`

确保已在项目根目录下运行 `uv sync`。

### Q: `anthropic.AuthenticationError`

检查 `.env` 文件中 `ANTHROPIC_API_KEY` 是否正确填写，且文件在项目根目录。

### Q: 调研速度很慢

- 设置 `SEMANTIC_SCHOLAR_API_KEY` 可大幅提升 API 调用速度
- 降低 `MAX_PAPERS_PER_EXPANSION` 和 `MAX_TOTAL_PAPERS` 可缩短时间

### Q: 在 Apple Silicon Mac 上安装 hdbscan 失败

```bash
brew install libomp
uv sync --extra clustering
```

### Q: 如何中断并恢复一个 Survey？

当前版本使用内存 checkpointer，程序退出后无法恢复。
如需持久化，可将 `build_graph()` 的 `checkpointer` 参数替换为 `SqliteSaver`：

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
checkpointer = AsyncSqliteSaver.from_conn_string("surveys.db")
```

---

## 9. 自定义 Prompt

`prompts/` 目录下的 Markdown 文件是 LLM 的系统提示词，可直接编辑以调整 Agent 行为：

- `dialogue_initial.md` - 调整对话风格和轮次
- `extraction_card.md` - 调整提取字段和格式
- `taxonomy_suggest.md` - 调整分类法建议标准
- `writer_section.md` - 调整写作风格和引用规范

> `writer_section.md` 中的 `{cite_key_list}` 占位符由程序自动填充，**请勿删除**。
