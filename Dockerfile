FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 安装系统依赖（pymupdf 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（先拷贝锁文件，利用 Docker 缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra web --no-install-project

# 拷贝项目源码
COPY src/ src/
COPY web/ web/
COPY prompts/ prompts/

# 安装项目本身
RUN uv sync --frozen --no-dev --extra web

# 创建数据目录
RUN mkdir -p data/surveys data/papers/unclassified data/papers/classified

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["uv", "run", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
