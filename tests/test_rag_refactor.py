"""
Testes para a refatoração do sistema RAG.

Cobre:
  - RAG (interface abstrata)
  - WeaviateRAG (mock do client Weaviate)
  - RagieRAG (mock do client Ragie)
  - WebSearch (interface abstrata)
  - TavilySearch (mock do client Tavily)
  - Composição TavilySearch + RAG storage
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from rag.base import RAG, TypeAccess
from search.base import WebSearch


# ===========================================================================
# Implementações concretas mínimas para testar as interfaces
# ===========================================================================

class _DummyRAG(RAG):
    name = "dummy"
    description = "Dummy RAG para testes."
    _store: List[Document] = []

    def search(self, query, *, k=None):
        return self._store[:k] if k else self._store

    def write(self, texts, metadatas=None, source_ids=None):
        metadatas = metadatas or [{} for _ in texts]
        for text, meta in zip(texts, metadatas):
            self._store.append(Document(page_content=text, metadata=meta))
        return [f"id-{i}" for i in range(len(texts))]


class _DummyWebSearch(WebSearch):
    name = "dummy_search"
    description = "Dummy WebSearch para testes."

    def fetch(self, query):
        return [Document(page_content=f"resultado para: {query}", metadata={"query": query})]


# ===========================================================================
# Testes: RAG base
# ===========================================================================

class TestRAGInterface:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            RAG()  # type: ignore

    def test_concrete_search_and_write(self):
        rag = _DummyRAG()
        rag._store = []
        ids = rag.write(["hello world"], [{"source": "test"}])
        assert len(ids) == 1

        docs = rag.search("hello")
        assert len(docs) == 1
        assert docs[0].page_content == "hello world"

    def test_as_retriever_returns_callable(self):
        rag = _DummyRAG()
        rag._store = [Document(page_content="doc1", metadata={})]
        retriever = rag.as_retriever(k=1)
        result = retriever("qualquer query")
        assert isinstance(result, list)
        assert result[0].page_content == "doc1"

    def test_as_tool_read_only(self):
        rag = _DummyRAG()
        rag._store = [Document(page_content="conteúdo relevante", metadata={})]
        tool = rag.as_tool(type_access=TypeAccess.READ)

        result = tool.func(query="busca")
        assert isinstance(result, list)
        assert result[0]["page_content"] == "conteúdo relevante"

        result = tool.func(text_to_save="não pode salvar")
        assert "não tem permissão de escrita" in result

    def test_as_tool_write_only(self):
        rag = _DummyRAG()
        rag._store = []
        tool = rag.as_tool(type_access=TypeAccess.WRITE)

        result = tool.func(text_to_save="novo dado")
        assert "salva com sucesso" in result

        result = tool.func(query="não pode buscar")
        assert "não tem permissão de leitura" in result

    def test_as_tool_all(self):
        rag = _DummyRAG()
        rag._store = []
        tool = rag.as_tool(type_access=TypeAccess.ALL)

        tool.func(text_to_save="dado x")
        result = tool.func(query="dado x")
        assert isinstance(result, list)

    def test_as_tool_no_params_returns_error(self):
        rag = _DummyRAG()
        tool = rag.as_tool(type_access=TypeAccess.READ)
        result = tool.func()
        assert "Erro" in result


# ===========================================================================
# Testes: WeaviateRAG
# ===========================================================================

class TestWeaviateRAG:
    def _make_rag(self):
        """Cria um WeaviateRAG com todos os externos mockados."""
        from rag.weaviate import WeaviateRAG
        from langchain_core.embeddings import Embeddings

        mock_embedding = MagicMock(spec=Embeddings)
        mock_client = MagicMock()
        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search.return_value = [
            Document(page_content="resultado weaviate", metadata={"src": "w"})
        ]
        mock_vectorstore.add_texts.return_value = ["weaviate-id-1"]
        mock_vectorstore.as_retriever.return_value = MagicMock()
        mock_ranker = MagicMock()

        class MyWeaviateRAG(WeaviateRAG):
            description = "Teste Weaviate."
            collection_name = "TEST_Collection"
            embedding = mock_embedding
            skip_init_checks = True
            port = 8080

        with patch("rag.weaviate.weaviate.connect_to_local", return_value=mock_client), \
             patch("rag.weaviate.WeaviateVectorStore", return_value=mock_vectorstore), \
             patch("rag.weaviate.Ranker", return_value=mock_ranker):
            rag = MyWeaviateRAG()
            rag.vectorstore = mock_vectorstore
            return rag

    def test_search_delegates_to_vectorstore(self):
        rag = self._make_rag()
        docs = rag.search("query teste")
        assert docs[0].page_content == "resultado weaviate"
        rag.vectorstore.similarity_search.assert_called_once()

    def test_write_splits_and_calls_add_texts(self):
        rag = self._make_rag()
        rag.vectorstore.add_texts.return_value = ["id-chunk-0"]
        ids = rag.write(["texto curto para salvar"], [{"meta": "valor"}])
        assert len(ids) == 1
        rag.vectorstore.add_texts.assert_called_once()

    def test_write_with_source_ids_uses_deterministic_uuids(self):
        import uuid
        rag = self._make_rag()
        rag.vectorstore.add_texts.return_value = ["some-id"]
        rag.write(["texto"], source_ids=["fonte-abc"])
        call_kwargs = rag.vectorstore.add_texts.call_args
        ids_passed = call_kwargs.kwargs.get("ids") or call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        if ids_passed is None and call_kwargs.kwargs:
            ids_passed = call_kwargs.kwargs.get("ids")
        assert ids_passed is not None
        assert uuid.UUID(ids_passed[0])  # deve ser UUID válido

    def test_smart_search_basic_no_rerank(self):
        rag = self._make_rag()
        rag.ranker = None
        docs = rag.smart_search("query", search_depth="basic")
        assert isinstance(docs, list)

    def test_as_tool_returns_structured_tool(self):
        from langchain_core.tools import StructuredTool
        rag = self._make_rag()
        tool = rag.as_tool()
        assert isinstance(tool, StructuredTool)

    def test_requires_description(self):
        from rag.weaviate import WeaviateRAG
        from langchain_core.embeddings import Embeddings

        class BadRAG(WeaviateRAG):
            collection_name = "X"
            embedding = MagicMock(spec=Embeddings)

        with patch("rag.weaviate.weaviate.connect_to_local"), \
             patch("rag.weaviate.WeaviateVectorStore"):
            with pytest.raises(ValueError, match="description"):
                BadRAG()


# ===========================================================================
# Testes: RagieRAG
# ===========================================================================

class TestRagieRAG:
    def _make_rag(self):
        from rag.ragie import RagieRAG

        mock_chunk = MagicMock()
        mock_chunk.text = "resultado ragie"
        mock_chunk.document_id = "doc-123"
        mock_chunk.score = 0.95
        mock_chunk.document_metadata = {"fonte": "ragie"}

        mock_response = MagicMock()
        mock_response.scored_chunks = [mock_chunk]

        mock_doc = MagicMock()
        mock_doc.id = "ragie-doc-id"

        mock_client = MagicMock()
        mock_client.retrievals.retrieve.return_value = mock_response
        mock_client.documents.create_raw.return_value = mock_doc

        class MyRagieRAG(RagieRAG):
            description = "Teste Ragie."
            partition = "test-partition"
            api_key = "fake-key"

        with patch.dict("sys.modules", {"ragie": MagicMock(Ragie=MagicMock(return_value=mock_client))}):
            rag = MyRagieRAG()
            rag._client = mock_client
            return rag

    def test_search_returns_documents(self):
        rag = self._make_rag()
        docs = rag.search("query ragie")
        assert len(docs) == 1
        assert docs[0].page_content == "resultado ragie"
        assert docs[0].metadata["document_id"] == "doc-123"
        assert docs[0].metadata["score"] == 0.95

    def test_search_passes_partition_and_top_k(self):
        rag = self._make_rag()
        rag.search("query", k=7)
        call_args = rag._client.retrievals.retrieve.call_args
        request = call_args.kwargs.get("request") or call_args.args[0]
        assert request["partition"] == "test-partition"
        assert request["top_k"] == 7

    def test_write_calls_create_raw(self):
        rag = self._make_rag()
        ids = rag.write(["texto para ragie"], [{"chave": "valor"}], source_ids=["src-001"])
        assert ids == ["ragie-doc-id"]
        call_args = rag._client.documents.create_raw.call_args
        request = call_args.kwargs.get("request") or call_args.args[0]
        assert request["partition"] == "test-partition"
        assert request["external_id"] == "src-001"

    def test_write_without_source_ids(self):
        rag = self._make_rag()
        ids = rag.write(["texto sem id"])
        assert ids == ["ragie-doc-id"]
        call_args = rag._client.documents.create_raw.call_args
        request = call_args.kwargs.get("request") or call_args.args[0]
        assert "external_id" not in request

    def test_requires_partition(self):
        from rag.ragie import RagieRAG

        class BadRAG(RagieRAG):
            description = "Sem partição."

        with patch.dict("sys.modules", {"ragie": MagicMock(Ragie=MagicMock())}):
            with pytest.raises(ValueError, match="partition"):
                BadRAG()

    def test_as_tool_returns_structured_tool(self):
        from langchain_core.tools import StructuredTool
        rag = self._make_rag()
        tool = rag.as_tool()
        assert isinstance(tool, StructuredTool)


# ===========================================================================
# Testes: WebSearch base
# ===========================================================================

class TestWebSearchInterface:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            WebSearch()  # type: ignore

    def test_fetch_returns_documents(self):
        ws = _DummyWebSearch()
        docs = ws.fetch("minha busca")
        assert len(docs) == 1
        assert "minha busca" in docs[0].page_content

    def test_as_tool_without_storage_returns_one_tool(self):
        ws = _DummyWebSearch()
        ws.storage = None
        tools = ws.as_tool()
        assert len(tools) == 1
        assert "WebSearch" in tools[0].name

    def test_as_tool_with_storage_returns_two_tools(self):
        ws = _DummyWebSearch()
        ws.storage = _DummyRAG()
        ws.storage._store = []
        tools = ws.as_tool()
        assert len(tools) == 2
        names = [t.name for t in tools]
        assert any("WebSearch" in n for n in names)
        assert any("ReadCache" in n for n in names)

    def test_cache_tool_returns_no_results_message(self):
        ws = _DummyWebSearch()
        ws.storage = _DummyRAG()
        ws.storage._store = []
        tools = ws.as_tool()
        cache_tool = next(t for t in tools if "ReadCache" in t.name)
        result = cache_tool.func("qualquer coisa")
        assert "Nenhum resultado" in result

    def test_cache_tool_returns_stored_docs(self):
        ws = _DummyWebSearch()
        ws.storage = _DummyRAG()
        ws.storage._store = [
            Document(page_content="conteúdo x", metadata={"title": "Doc X", "url": "http://x.com"})
        ]
        tools = ws.as_tool()
        cache_tool = next(t for t in tools if "ReadCache" in t.name)
        result = cache_tool.func("x")
        assert "Doc X" in result


# ===========================================================================
# Testes: TavilySearch
# ===========================================================================

class TestTavilySearch:
    def _mock_tavily_response(self):
        return {
            "answer": "Resposta resumida da AI.",
            "results": [
                {
                    "title": "Artigo Relevante",
                    "url": "https://exemplo.com/artigo",
                    "content": "Conteúdo detalhado do artigo sobre o tema buscado.",
                }
            ],
        }

    def _make_search(self, storage=None):
        from search.tavily import TavilySearch

        mock_client = MagicMock()
        mock_client.search.return_value = self._mock_tavily_response()

        class MyTavily(TavilySearch):
            description = "Busca Tavily de teste."
            tavily_api_key = "fake-tavily-key"

        with patch("search.tavily.TavilyClient", return_value=mock_client):
            ts = MyTavily()
            ts._client = mock_client
            ts.storage = storage
            return ts

    def test_fetch_returns_documents(self):
        ts = self._make_search()
        docs = ts.fetch("python asyncio")
        assert len(docs) == 2  # answer + 1 result
        assert "Resumo AI" in docs[0].page_content
        assert "Artigo Relevante" in docs[1].page_content

    def test_fetch_without_answer(self):
        ts = self._make_search()
        ts._client.search.return_value = {
            "answer": "",
            "results": [{"title": "T", "url": "http://t.com", "content": "conteúdo"}],
        }
        docs = ts.fetch("query")
        assert len(docs) == 1

    def test_fetch_stores_in_storage(self):
        storage = _DummyRAG()
        storage._store = []
        ts = self._make_search(storage=storage)
        ts.fetch("query com storage")
        assert len(storage._store) > 0

    def test_fetch_without_storage_does_not_persist(self):
        ts = self._make_search(storage=None)
        docs = ts.fetch("query sem storage")
        assert isinstance(docs, list)

    def test_as_tool_without_storage_one_tool(self):
        ts = self._make_search(storage=None)
        tools = ts.as_tool()
        assert len(tools) == 1

    def test_as_tool_with_storage_two_tools(self):
        storage = _DummyRAG()
        storage._store = []
        ts = self._make_search(storage=storage)
        tools = ts.as_tool()
        assert len(tools) == 2

    def test_as_tool_web_search_calls_fetch(self):
        ts = self._make_search()
        tools = ts.as_tool()
        web_tool = tools[0]
        result = web_tool.func("busca via tool")
        assert isinstance(result, list)
        ts._client.search.assert_called()


# ===========================================================================
# Testes: Composição TavilySearch + RAG storage
# ===========================================================================

class TestComposition:
    """
    Verifica o padrão de composição:
    TavilySearch busca na web e persiste no RAG de escolha.
    """

    def test_tavily_with_weaviate_storage(self):
        """TavilySearch pode usar qualquer RAG como storage."""
        from search.tavily import TavilySearch

        mock_rag = MagicMock(spec=RAG)
        mock_rag.search.return_value = [Document(page_content="cache hit", metadata={})]
        mock_rag.write.return_value = ["id-1"]

        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {
            "answer": "resumo",
            "results": [{"title": "T", "url": "http://t.com", "content": "texto"}],
        }

        class MySearch(TavilySearch):
            description = "Composição de teste."
            tavily_api_key = "key"

        with patch("search.tavily.TavilyClient", return_value=mock_tavily_client):
            ts = MySearch()
            ts._client = mock_tavily_client
            ts.storage = mock_rag

        docs = ts.fetch("busca composta")
        mock_rag.write.assert_called_once()

        tools = ts.as_tool()
        assert len(tools) == 2

        cache_tool = next(t for t in tools if "ReadCache" in t.name)
        result = cache_tool.func("cache hit?")
        assert "cache hit" in result

    def test_swap_storage_backend(self):
        """Trocar o backend de storage não requer mudar o TavilySearch."""
        from search.tavily import TavilySearch

        weaviate_mock = MagicMock(spec=RAG)
        weaviate_mock.write.return_value = ["w-id"]
        ragie_mock = MagicMock(spec=RAG)
        ragie_mock.write.return_value = ["r-id"]

        mock_tavily_client = MagicMock()
        mock_tavily_client.search.return_value = {
            "answer": "",
            "results": [{"title": "T", "url": "http://t.com", "content": "x"}],
        }

        class MySearch(TavilySearch):
            description = "Swap test."
            tavily_api_key = "key"

        with patch("search.tavily.TavilyClient", return_value=mock_tavily_client):
            ts = MySearch()
            ts._client = mock_tavily_client

        ts.storage = weaviate_mock
        ts.fetch("query 1")
        weaviate_mock.write.assert_called_once()
        ragie_mock.write.assert_not_called()

        ts.storage = ragie_mock
        ts.fetch("query 2")
        ragie_mock.write.assert_called_once()
