# -*- coding: utf-8 -*-
"""
modules/vector_memory.py — ArielOS 向量記憶層

支援三層 Backend，自動偵測可用環境：

  Tier 1: Qdrant (本地記憶體模式) + sentence-transformers
          → 支援 Python 3.14，最完整的語意搜尋
          → pip install qdrant-client sentence-transformers

  Tier 2: NumPy 純計算 (Cosine Similarity) + sentence-transformers
          → 零外部向量DB，只需 numpy + sentence-transformers
          → 資料存於 JSON，重啟後自動重建索引

  Tier 3: 停用 (Graceful Degradation)
          → 所有方法返回空結果，系統正常運行

安裝建議 (Python 3.14+):
  pip install qdrant-client sentence-transformers
"""

import json
import threading
import math
from pathlib import Path
from .config import BASE_DIR, log

# ── Backend 偵測 ──────────────────────────────────────────────────────────────

_qdrant_available = False
_st_available = False
_BACKEND = "disabled"  # "qdrant" | "numpy" | "disabled"

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    _qdrant_available = True
except Exception as e:
    log(f"⚠️ [VectorMemory] qdrant-client 未安裝或不相容 ({type(e).__name__})")

try:
    from sentence_transformers import SentenceTransformer
    _st_available = True
except Exception as e:
    log(f"⚠️ [VectorMemory] sentence-transformers 未安裝 ({type(e).__name__})")

if _qdrant_available and _st_available:
    _BACKEND = "qdrant"
elif _st_available:
    _BACKEND = "numpy"
else:
    _BACKEND = "disabled"

log(f"📦 [VectorMemory] Backend 選定: {_BACKEND.upper()}")


# ── 向量記憶管理器 ────────────────────────────────────────────────────────────

class VectorMemoryManager:
    """
    向量化語意記憶管理器。
    自動選用最佳可用 Backend：Qdrant → NumPy → Disabled。
    """

    _VECTOR_DIM = 384  # paraphrase-multilingual-MiniLM-L12-v2 輸出維度
    _MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
    _instance = None

    def __new__(cls, base_dir: Path = BASE_DIR):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, base_dir: Path = BASE_DIR):
        if self._initialized:
            return
        self._initialized = True
        self._ready = False
        self._lock = threading.Lock()
        self._base_dir = Path(base_dir)

        global _BACKEND
        if _BACKEND == "disabled":
            log("ℹ️ [VectorMemory] 向量記憶停用。安裝 sentence-transformers 以啟用。")
            return

        try:
            log(f"🤖 [VectorMemory] 載入 Embedding 模型: {self._MODEL_NAME}...")
            self._encoder = SentenceTransformer(self._MODEL_NAME)

            if _BACKEND == "qdrant":
                try:
                    self._init_qdrant()
                except Exception as e:
                    log(f"⚠️ [VectorMemory] Qdrant 初始化失敗 ({e})，降級至 NumPy。")
                    _BACKEND = "numpy"

            if _BACKEND == "numpy":
                self._init_numpy()

            self._ready = True
            log(f"✅ [VectorMemory] 初始化完成 (Backend: {_BACKEND.upper()})")
        except Exception as e:
            log(f"❌ [VectorMemory] 初始化失敗: {e}")

    def _init_qdrant(self):
        """初始化 Qdrant 本地記憶體模式 (無需 Docker)"""
        self._qdrant = QdrantClient(":memory:")
        self._qdrant_collections = set()  # 已建立的 collection 名稱

    def _get_qdrant_collection(self, agent_id: str) -> str:
        """確保 Qdrant Collection 存在，返回 collection 名稱"""
        name = f"arielos_{agent_id.replace('-', '_').lower()}"
        if name not in self._qdrant_collections:
            try:
                self._qdrant.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=self._VECTOR_DIM, distance=Distance.COSINE)
                )
                self._qdrant_collections.add(name)
            except Exception:
                pass  # 可能已存在
        return name

    def _init_numpy(self):
        """初始化 NumPy fallback 模式 (JSON + 餘弦相似度)"""
        self._numpy_store_path = self._base_dir / "Shared_Vault" / "Memory" / "vector_store.json"
        self._numpy_store_path.parent.mkdir(parents=True, exist_ok=True)
        # 記憶結構: { agent_id: [ {id, text, vector, metadata}, ... ] }
        self._numpy_store: dict = {}
        if self._numpy_store_path.exists():
            try:
                with open(self._numpy_store_path, "r", encoding="utf-8") as f:
                    self._numpy_store = json.load(f)
                total = sum(len(v) for v in self._numpy_store.values())
                log(f"📂 [VectorMemory] NumPy 索引已從磁碟還原 ({total} 筆)")
            except Exception:
                self._numpy_store = {}

    def _numpy_save(self):
        """將 NumPy 記憶索引寫回 JSON（不含 vector 以外的大物件）"""
        try:
            with open(self._numpy_store_path, "w", encoding="utf-8") as f:
                json.dump(self._numpy_store, f, ensure_ascii=False)
        except Exception as e:
            log(f"⚠️ [VectorMemory] 索引儲存失敗: {e}")

    @staticmethod
    def _cosine(v1: list, v2: list) -> float:
        """純 Python 餘弦相似度（不依賴 numpy）"""
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)

    # ── 公開 API ──────────────────────────────────────────────────────────────

    def add_fact(self, agent_id: str, fact_id: str, text: str, metadata: dict | None = None) -> bool:
        """向量化並儲存一筆事實"""
        if not self._ready:
            return False
        try:
            embedding = self._encoder.encode([text])[0].tolist()

            if _BACKEND == "qdrant":
                col = self._get_qdrant_collection(agent_id)
                # Qdrant 需要整數 ID，使用 hash
                int_id = abs(hash(fact_id)) % (2 ** 63)
                self._qdrant.upsert(
                    collection_name=col,
                    points=[PointStruct(id=int_id, vector=embedding,
                                        payload={**(metadata or {}), "fact_id": fact_id, "text": text})]
                )
            else:  # numpy
                with self._lock:
                    store = self._numpy_store.setdefault(agent_id, [])
                    # 更新或新增
                    for item in store:
                        if item["id"] == fact_id:
                            item["vector"] = embedding
                            item["metadata"] = metadata or {}
                            break
                    else:
                        store.append({"id": fact_id, "text": text,
                                      "vector": embedding, "metadata": metadata or {}})
                    # 限制每代理人最多 2000 筆
                    if len(store) > 2000:
                        self._numpy_store[agent_id] = store[-2000:]
                    self._numpy_save()
            return True
        except Exception as e:
            log(f"⚠️ [VectorMemory] add_fact 失敗: {e}")
            return False

    def query_semantic(self, agent_id: str, query: str, top_k: int = 3) -> list[dict]:
        """語意相似度查詢"""
        if not self._ready:
            return []
        try:
            embedding = self._encoder.encode([query])[0].tolist()

            if _BACKEND == "qdrant":
                col = self._get_qdrant_collection(agent_id)
                hits = self._qdrant.search(
                    collection_name=col, query_vector=embedding, limit=top_k
                )
                results = []
                for h in hits:
                    score = h.score
                    if score < 0.4:
                        continue
                    payload = h.payload or {}
                    results.append({
                        "id": payload.get("fact_id", str(h.id)),
                        "text": payload.get("text", ""),
                        "score": round(score, 3),
                        "metadata": {k: v for k, v in payload.items() if k not in ("fact_id", "text")}
                    })
            else:  # numpy
                store = self._numpy_store.get(agent_id, [])
                if not store:
                    return []
                scored = []
                for item in store:
                    score = self._cosine(embedding, item["vector"])
                    if score >= 0.4:
                        scored.append((score, item))
                scored.sort(key=lambda x: x[0], reverse=True)
                results = [
                    {"id": item["id"], "text": item["text"],
                     "score": round(score, 3), "metadata": item.get("metadata", {})}
                    for score, item in scored[:top_k]
                ]

            if results:
                log(f"🔍 [VectorMemory] 語意查詢命中 {len(results)} 筆 ({_BACKEND})")
            return results
        except Exception as e:
            log(f"⚠️ [VectorMemory] query_semantic 失敗: {e}")
            return []

    def delete_fact(self, agent_id: str, fact_id: str) -> bool:
        """刪除一筆事實"""
        if not self._ready:
            return False
        try:
            if _BACKEND == "qdrant":
                col = self._get_qdrant_collection(agent_id)
                int_id = abs(hash(fact_id)) % (2 ** 63)
                self._qdrant.delete(collection_name=col,
                                    points_selector=[int_id])
            else:
                with self._lock:
                    store = self._numpy_store.get(agent_id, [])
                    self._numpy_store[agent_id] = [i for i in store if i["id"] != fact_id]
                    self._numpy_save()
            return True
        except Exception as e:
            log(f"⚠️ [VectorMemory] delete_fact 失敗: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def backend(self) -> str:
        return _BACKEND


# 全域單例
VM = VectorMemoryManager(BASE_DIR)
