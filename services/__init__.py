"""LeadFlow 知识库检索管道服务层。

提供：
  - embedding_service  : Embedding 向量生成（DeepSeek/OpenAI 兼容 API）
  - rerank_service     : Cross-Encoder 精排（BGE/Jina/Cohere）
  - chunk_store        : OceanBase 原生混合检索（Vector + BM25）
  - retrieval_pipeline : 完整四阶段检索管道
"""
