FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（pymupdf 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml .
COPY src/ src/
COPY web/ web/
COPY prompts/ prompts/

# 安装核心依赖 + web 依赖
RUN pip install --no-cache-dir -e ".[web]"

# 创建数据目录
RUN mkdir -p data/surveys data/papers/unclassified data/papers/classified

# 暴露端口
EXPOSE 8080

# 启动命令
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
