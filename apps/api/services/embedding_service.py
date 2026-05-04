from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from apps.api.schemas.annotations import AnnotationRecord
from apps.api.schemas.episodes import EpisodeListItem
from apps.api.schemas.search import SearchResult, SemanticSearchRequest
from packages.robot_schema import build_embeddings_pyarrow_schema


EMBEDDING_DIM = 64
SOURCE_MODEL = "deterministic-text-hash-v1"
EMBEDDING_STORAGE_ROOT = Path("data/lance/embeddings")


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
    ) -> None:
        self.storage_root = storage_root
        self.persist = persist
        self.mirror_lance = mirror_lance
        self.mirror_lancedb = mirror_lancedb
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
        records: list[EmbeddingRecord] = []
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
                records.append(
                    EmbeddingRecord(
                        embedding_id=_embedding_id(
                            payload_dataset_id=dataset_id,
                            scope=f"episode:{episode.episode_index}",
                            text=text,
                        ),
                        episode_index=episode.episode_index,
                        frame_index=None,
                        clip_start_frame=0,
                        clip_end_frame=episode.length,
                        modality="text",
                        embedding=embed_text(text),
                        text=text,
                        source_model=SOURCE_MODEL,
                        created_at=now,
                    )
                )

        for annotation in annotations:
            text = f"{annotation.label_type} {annotation.label_value} {annotation.review_status}"
            records.append(
                EmbeddingRecord(
                    embedding_id=_embedding_id(
                        payload_dataset_id=dataset_id,
                        scope=f"annotation:{annotation.annotation_id}",
                        text=text,
                    ),
                    episode_index=annotation.episode_index,
                    frame_index=annotation.start_frame if annotation.start_frame == annotation.end_frame else None,
                    clip_start_frame=annotation.start_frame,
                    clip_end_frame=annotation.end_frame,
                    modality="text",
                    embedding=embed_text(text),
                    text=text,
                    source_model=SOURCE_MODEL,
                    created_at=now,
                )
            )

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
        query_embedding = embed_text(payload.text)
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


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in "".join(char.lower() if char.isalnum() else " " for char in text).split()
        if token
    ]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(l_value * r_value for l_value, r_value in zip(left, right))


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
