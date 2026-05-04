from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import SearchResult, SemanticSearchRequest
from packages.robot_schema import build_embeddings_pyarrow_schema


EMBEDDING_DIM = 64
SOURCE_MODEL = "deterministic-text-hash-v1"
EMBEDDING_STORAGE_ROOT = Path("data/lance/embeddings")
OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class EmbeddingRecord:
    embedding_id: str
    episode_index: int
    frame_index: int | None
    clip_start_frame: int | None
    clip_end_frame: int | None
    modality: str
    embedding: list[float]
    text: str
    source_model: str
    created_at: datetime


@dataclass(frozen=True)
class EmbeddingSource:
    scope: str
    episode_index: int
    frame_index: int | None
    clip_start_frame: int | None
    clip_end_frame: int | None
    modality: str
    text: str


@dataclass(frozen=True)
class EmbeddedText:
    embedding: list[float]
    source_model: str


class TextEmbeddingProvider(Protocol):
    source_model: str

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        ...


class DeterministicTextEmbeddingProvider:
    source_model = SOURCE_MODEL

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [embed_text(text) for text in texts]


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("ROBOT_DATA_STUDIO_EMBEDDING_API_KEY")
            or os.getenv("ROBOT_DATA_STUDIO_VLM_API_KEY")
        )
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("ROBOT_DATA_STUDIO_EMBEDDING_BASE_URL", OPENAI_COMPATIBLE_BASE_URL)
        ).rstrip("/")
        self.model = model or os.getenv(
            "ROBOT_DATA_STUDIO_EMBEDDING_MODEL",
            "text-embedding-3-small",
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.getenv("ROBOT_DATA_STUDIO_EMBEDDING_TIMEOUT_SECONDS", "90"))
        )
        self.source_model = f"openai-compatible:{self.model}"

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._requires_api_key() and not self.api_key:
            raise RuntimeError(
                "ROBOT_DATA_STUDIO_EMBEDDING_API_KEY is required for the default OpenAI endpoint."
            )
        response = self._post_json(
            {
                "model": self.model,
                "input": texts,
            }
        )
        rows = response.get("data")
        if not isinstance(rows, list):
            raise ValueError("Embedding response missing data list")
        ordered = sorted(
            (row for row in rows if isinstance(row, dict)),
            key=lambda row: int(row.get("index", 0)),
        )
        embeddings = [row.get("embedding") for row in ordered]
        if len(embeddings) != len(texts):
            raise ValueError("Embedding response count does not match input count")
        return [_normalize_embedding(embedding) for embedding in embeddings]

    def _requires_api_key(self) -> bool:
        return self.base_url == OPENAI_COMPATIBLE_BASE_URL

    def _post_json(self, body: dict[str, object]) -> dict[str, object]:
        url = f"{self.base_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class EmbeddingIndex:
    """Small deterministic embedding index for local semantic search.

    LanceDB is used opportunistically when installed. Keeping the deterministic
    path explicit lets the app use semantic search without requiring model
    weights or optional vector-search dependencies.
    """

    def __init__(
        self,
        storage_root: Path = EMBEDDING_STORAGE_ROOT,
        *,
        persist: bool = True,
        mirror_lance: bool = True,
        mirror_lancedb: bool = True,
        embedding_provider: TextEmbeddingProvider | None = None,
    ) -> None:
        self.storage_root = storage_root
        self.persist = persist
        self.mirror_lance = mirror_lance
        self.mirror_lancedb = mirror_lancedb
        self.embedding_provider = embedding_provider or get_text_embedding_provider()
        self._records: dict[str, list[EmbeddingRecord]] = {}
        if self.persist:
            self._load_records()

    def index_dataset(
        self,
        dataset_id: str,
        episodes: list[EpisodeListItem],
        annotations: list[AnnotationRecord],
    ) -> list[EmbeddingRecord]:
        now = datetime.now(timezone.utc)
        sources: list[EmbeddingSource] = []
        for episode in episodes:
            text = " ".join(
                part
                for part in (
                    episode.caption,
                    f"task {episode.task_index}" if episode.task_index is not None else None,
                    f"success {episode.success_label}" if episode.success_label is not None else None,
                    f"review {episode.review_status}",
                )
                if part
            )
            if text:
                sources.append(
                    EmbeddingSource(
                        scope=f"episode:{episode.episode_index}",
                        episode_index=episode.episode_index,
                        frame_index=None,
                        clip_start_frame=0,
                        clip_end_frame=episode.length,
                        modality="text",
                        text=text,
                    )
                )

        for annotation in annotations:
            text = f"{annotation.label_type} {annotation.label_value} {annotation.review_status}"
            sources.append(
                EmbeddingSource(
                    scope=f"annotation:{annotation.annotation_id}",
                    episode_index=annotation.episode_index,
                    frame_index=(
                        annotation.start_frame
                        if annotation.start_frame == annotation.end_frame
                        else None
                    ),
                    clip_start_frame=annotation.start_frame,
                    clip_end_frame=annotation.end_frame,
                    modality="text",
                    text=text,
                )
            )

        embeddings = self._embed_texts([source.text for source in sources])
        records = [
            EmbeddingRecord(
                embedding_id=_embedding_id(
                    payload_dataset_id=dataset_id,
                    scope=source.scope,
                    text=source.text,
                ),
                episode_index=source.episode_index,
                frame_index=source.frame_index,
                clip_start_frame=source.clip_start_frame,
                clip_end_frame=source.clip_end_frame,
                modality=source.modality,
                embedding=embedded.embedding,
                text=source.text,
                source_model=embedded.source_model,
                created_at=now,
            )
            for source, embedded in zip(sources, embeddings)
        ]
        self._records[dataset_id] = records
        self._persist_dataset(dataset_id)
        return records

    def search(
        self,
        payload: SemanticSearchRequest,
        episodes: list[EpisodeListItem],
        annotations: list[AnnotationRecord],
    ) -> list[SearchResult]:
        records = self.index_dataset(payload.dataset_id, episodes, annotations)
        query_embedding = self._embed_text(payload.text).embedding
        lancedb_results = self._search_lancedb(
            payload.dataset_id,
            query_embedding=query_embedding,
            limit=payload.limit,
        )
        if lancedb_results is not None:
            return lancedb_results

        scored = [
            (cosine_similarity(query_embedding, record.embedding), record)
            for record in records
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                dataset_id=payload.dataset_id,
                episode_index=record.episode_index,
                frame_index=record.frame_index,
                score=score,
                match_type="semantic_text_embedding",
                label=record.text,
            )
            for score, record in scored[: payload.limit]
            if score > 0
        ]

    def _embed_text(self, text: str) -> EmbeddedText:
        return self._embed_texts([text])[0]

    def _embed_texts(self, texts: list[str]) -> list[EmbeddedText]:
        if not texts:
            return []
        try:
            embeddings = self.embedding_provider.embed_many(texts)
            if len(embeddings) != len(texts):
                raise ValueError("Embedding provider returned the wrong number of vectors")
            source_model = self.embedding_provider.source_model
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError):
            fallback = DeterministicTextEmbeddingProvider()
            embeddings = fallback.embed_many(texts)
            source_model = fallback.source_model
        return [
            EmbeddedText(embedding=_normalize_embedding(embedding), source_model=source_model)
            for embedding in embeddings
        ]

    def records(self, dataset_id: str) -> list[EmbeddingRecord]:
        return self._records.get(dataset_id, [])

    def storage_paths(self, dataset_id: str) -> dict[str, str]:
        dataset_dir = self._dataset_dir(dataset_id)
        return {
            "jsonl": str(dataset_dir / "embeddings.jsonl"),
            "lance": str(dataset_dir / "embeddings.lance"),
            "lancedb": str(dataset_dir / "lancedb"),
        }

    def _load_records(self) -> None:
        if not self.storage_root.exists():
            return
        for jsonl_path in self.storage_root.glob("*/embeddings.jsonl"):
            records = []
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["created_at"] = datetime.fromisoformat(row["created_at"])
                records.append(EmbeddingRecord(**row))
            if records:
                dataset_id = json.loads((jsonl_path.parent / "dataset.json").read_text(encoding="utf-8"))[
                    "dataset_id"
                ]
                self._records[dataset_id] = records

    def _persist_dataset(self, dataset_id: str) -> None:
        if not self.persist:
            return
        dataset_dir = self._dataset_dir(dataset_id)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        (dataset_dir / "dataset.json").write_text(
            json.dumps({"dataset_id": dataset_id}, sort_keys=True),
            encoding="utf-8",
        )
        records = self.records(dataset_id)
        rows = [self._json_row(record) for record in records]
        (dataset_dir / "embeddings.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        self._mirror_lance(dataset_dir / "embeddings.lance", records)
        self._mirror_lancedb(dataset_dir / "lancedb", records)

    def _mirror_lance(self, lance_path: Path, records: list[EmbeddingRecord]) -> None:
        if not self.mirror_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_embeddings_pyarrow_schema()
        rows = [self._lance_row(record) for record in records]
        if rows:
            table = pa.Table.from_pylist(rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

    def _mirror_lancedb(self, database_path: Path, records: list[EmbeddingRecord]) -> None:
        if not self.mirror_lancedb or not records:
            return
        try:
            import lancedb
        except ImportError:
            return

        rows = [self._lancedb_row(record) for record in records]
        database_path.mkdir(parents=True, exist_ok=True)
        try:
            db = lancedb.connect(str(database_path))
            db.create_table("embeddings", data=rows, mode="overwrite")
        except Exception:
            return

    def _search_lancedb(
        self,
        dataset_id: str,
        *,
        query_embedding: list[float],
        limit: int,
    ) -> list[SearchResult] | None:
        database_path = self._dataset_dir(dataset_id) / "lancedb"
        if not database_path.exists():
            return None
        try:
            import lancedb
        except ImportError:
            return None
        try:
            db = lancedb.connect(str(database_path))
            table = db.open_table("embeddings")
            try:
                query = table.search(query_embedding, vector_column_name="embedding")
            except TypeError:
                query = table.search(query_embedding)
            rows = query.limit(limit).to_list()
        except Exception:
            return None
        return [
            SearchResult(
                dataset_id=dataset_id,
                episode_index=int(row["episode_index"]),
                frame_index=row.get("frame_index"),
                score=_score_from_distance(row.get("_distance")),
                match_type="lancedb_vector",
                label=row.get("text"),
            )
            for row in rows
        ]

    def _dataset_dir(self, dataset_id: str) -> Path:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._-")
        digest = hashlib.sha1(dataset_id.encode("utf-8")).hexdigest()[:12]
        return self.storage_root / f"{slug[:80] or 'dataset'}-{digest}"

    @staticmethod
    def _json_row(record: EmbeddingRecord) -> dict[str, object]:
        return {
            **asdict(record),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _lance_row(record: EmbeddingRecord) -> dict[str, object]:
        return asdict(record)

    @staticmethod
    def _lancedb_row(record: EmbeddingRecord) -> dict[str, object]:
        return {
            **asdict(record),
            "created_at": record.created_at.isoformat(),
        }


def embed_text(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def get_text_embedding_provider() -> TextEmbeddingProvider:
    provider_name = os.getenv("ROBOT_DATA_STUDIO_EMBEDDING_PROVIDER", "").lower()
    if provider_name in {"openai", "openai-compatible"}:
        return OpenAICompatibleEmbeddingProvider()
    return DeterministicTextEmbeddingProvider()


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in "".join(char.lower() if char.isalnum() else " " for char in text).split()
        if token
    ]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(l_value * r_value for l_value, r_value in zip(left, right))


def _normalize_embedding(value: object) -> list[float]:
    if not isinstance(value, list):
        raise ValueError("Embedding vector must be a list")
    vector = [float(item) for item in value]
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [item / norm for item in vector]


def _score_from_distance(distance: object) -> float | None:
    if distance is None:
        return None
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return None
    return 1.0 / (1.0 + max(0.0, value))


def _embedding_id(payload_dataset_id: str, scope: str, text: str) -> str:
    digest = hashlib.sha1(f"{payload_dataset_id}|{scope}|{text}".encode("utf-8")).hexdigest()
    return digest


embedding_index = EmbeddingIndex()
