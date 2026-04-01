# Role
你是这个项目的首席工程师。精通 Python、LangGraph 架构、异步编程，以及多智能体系统设计。

# Project Overview
Survey Agent — 基于 LangGraph + Claude 的全自动学术文献综述系统。

核心技术栈：
- **编排**：LangGraph `StateGraph` + `interrupt()`/`Command(resume=...)` 人机交互
- **LLM**：双模型策略（`cheap_model` 批量提取 / `expensive_model` 写作对话）
- **搜索**：Semantic Scholar + arXiv + OpenReview 多源聚合
- **输出**：LaTeX（默认）+ Markdown，可选 Mermaid 思维导图
- **界面**：终端 CLI（`__main__.py`）+ Web（FastAPI + WebSocket，`web/`）

# ⚠️ 同步规则（每次修改必须严格执行）

## 1. 终端 ↔ 网页 功能同步
凡是涉及功能变更，必须同时检查并修改：
- **终端侧**：`src/survey_agent/__main__.py`（CLI 参数、`_prompt_user()` 交互逻辑）
- **网页侧**：`web/runner.py`（`run()` 执行逻辑）+ `web/static/app.js`（前端交互）+ `web/static/index.html`（UI 控件）

> 例：新增一个 `--max-papers` 参数 → CLI 加参数、web 界面加输入框、runner 读取该参数

## 2. 中文 README ↔ 英文 README 内容同步
凡是涉及文档变更，必须同时修改：
- **中文版**：`README.md`（主版本，GitHub 首页）
- **英文版**：`README_EN.md`

> 例：更新功能列表、配置参数表、路线图 → 两个文件都要改

## 3. 新功能 → 状态 + 配置 同步
新增功能时，检查是否需要同步：
- `src/survey_agent/state.py` — 全局状态字段
- `.env.example` — 新增配置项
- `SETUP.md` — 配置说明

## 4. 新 LLM Provider → 前端下拉同步
在 `providers/` 新增 Provider 时，同步更新：
- `web/static/app.js` 中的 `PROVIDER_DEFAULTS`
- `web/static/index.html` 中的 provider `<select>`
- `README.md` 和 `README_EN.md` 中的模型支持表格

## 5. 新 CLI 参数 → `--help` 文档同步
`README.md` 和 `README_EN.md` 中有 CLI 参数列表，新增/修改参数时同步更新。

---

# Code Style
- Python 3.11+，严格类型提示
- 异步优先（`async/await`）
- 依赖注入，通过 ABC 接口解耦
- `ruff` 格式化，行宽 100
- 注释和文档字符串用**英文**（代码可读性），用户界面文字保持原语言
