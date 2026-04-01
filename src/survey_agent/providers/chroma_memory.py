"""
providers/chroma_memory.py - ChromaDB 向量记忆库实现

安装依赖 (可选):
    pip install "survey-agent[clustering]"
    # 或: pip install chromadb sentence-transformers

注入接口 (VectorMemory):
    memory = ChromaVectorMemory(
        persist_dir="data/chroma",
        collection_name="survey_papers",
    )
    agent = TaxonomyAgent(memory=memory)

TODO: 注入真实实现前需完成以下配置:
1. 安装 chromadb: pip install chromadb
2. 安装 sentence-transformers: pip install sentence-transformers
3. 设置 CHROMA_PERSIST_DIR 环境变量（或传入 persist_dir 参数）
"""

from __future__ import annotations

from typing import Any

from survey_agent.interfaces.memory import VectorMemory


class ChromaVectorMemory(VectorMemory):
    """
    基于 ChromaDB 的本地向量记忆库实现。

    使用 sentence-transformers 生成文本嵌入向量，
    数据持久化存储在本地磁盘。
    """

    def __init__(
        self,
        persist_dir: str = "data/chroma",
        collection_name: str = "survey_papers",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        """
        Args:
            persist_dir: ChromaDB 本地持久化路径
            collection_name: 向量集合名称
            embedding_model: sentence-transformers 模型名（影响语义质量）

        TODO: Inject ChromaDB + sentence-transformers here
        """
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._embedding_model = embedding_model

        # ── TODO: 注入 ChromaDB 实例 ─────────────────────────────────────────
        # 取消注释以下代码并安装依赖后即可使用:
        #
        # import chromadb
        # from chromadb.utils import embedding_functions
        #
        # self._client = chromadb.PersistentClient(path=persist_dir)
        # emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        #     model_name=embedding_model
        # )
        # self._collection = self._client.get_or_create_collection(
        #     name=collection_name,
        #     embedding_function=emb_fn,
        #     metadata={"hnsw:space": "cosine"},
        # )
        # ─────────────────────────────────────────────────────────────────────
        self._collection = None  # 未初始化标志

    def _check_initialized(self) -> None:
        if self._collection is None:
            raise NotImplementedError(
                "ChromaDB 未初始化。\n"
                "请安装依赖: pip install 'survey-agent[clustering]'\n"
                "并取消注释 providers/chroma_memory.py 中的 TODO 代码块。"
            )

    async def add_paper(self, paper_id: str, text: str, metadata: dict[str, Any]) -> None:
        self._check_initialized()
        raise NotImplementedError("TODO: Inject ChromaDB implementation")

    async def search_similar(
        self,
        query_text: str,
        limit: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self._check_initialized()
        raise NotImplementedError("TODO: Inject ChromaDB implementation")

    async def delete_paper(self, paper_id: str) -> None:
        self._check_initialized()
        raise NotImplementedError("TODO: Inject ChromaDB implementation")

    async def get_all_embeddings(self) -> dict[str, list[float]]:
        self._check_initialized()
        raise NotImplementedError("TODO: Inject ChromaDB implementation")
