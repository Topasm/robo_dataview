from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from packages.robot_schema import build_versions_pyarrow_schema


VERSION_STORAGE_ROOT = Path("data/lance/versions")


@dataclass(frozen=True)
class VersionRecord:
    version_id: str
    parent_version_id: str | None
    dataset_id: str
    description: str | None
    filter_query: str | None
    num_episodes: int
    num_frames: int
    export_format: str
    export_uri: str | None
    created_at: datetime
    created_by: str


class VersionStore:
    def __init__(
        self,
        storage_root: Path = VERSION_STORAGE_ROOT,
        *,
        mirror_lance: bool = True,
    ) -> None:
        self.storage_root = storage_root
        self.mirror_lance = mirror_lance
        self._records = self._load_records()

    def append(self, record: VersionRecord) -> VersionRecord:
        self._records = [existing for existing in self._records if existing.version_id != record.version_id]
        self._records.append(record)
        self._persist()
        return record

    def list(self, dataset_id: str | None = None) -> list[VersionRecord]:
        records = self._records
        if dataset_id is not None:
            records = [record for record in records if record.dataset_id == dataset_id]
        return sorted(records, key=lambda record: record.created_at)

    def storage_paths(self) -> dict[str, str]:
        return {
            "jsonl": str(self.storage_root / "versions.jsonl"),
            "lance": str(self.storage_root / "versions.lance"),
        }

    def _load_records(self) -> list[VersionRecord]:
        jsonl_path = self.storage_root / "versions.jsonl"
        if not jsonl_path.exists():
            return []
        records = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            row["created_at"] = datetime.fromisoformat(row["created_at"])
            records.append(VersionRecord(**row))
        return records

    def _persist(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        rows = [self._json_row(record) for record in self._records]
        (self.storage_root / "versions.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        self._mirror_lance(self.storage_root / "versions.lance", self._records)

    def _mirror_lance(self, lance_path: Path, records: list[VersionRecord]) -> None:
        if not self.mirror_lance:
            return
        try:
            import pyarrow as pa
            import lance
        except ImportError:
            return

        schema = build_versions_pyarrow_schema()
        rows = [self._lance_row(record) for record in records]
        if rows:
            table = pa.Table.from_pylist(rows, schema=schema)
        else:
            table = pa.Table.from_arrays(
                [pa.array([], type=field.type) for field in schema],
                schema=schema,
            )
        lance.write_dataset(table, str(lance_path), mode="overwrite")

    @staticmethod
    def _json_row(record: VersionRecord) -> dict[str, object]:
        return {
            **asdict(record),
            "created_at": record.created_at.isoformat(),
        }

    @staticmethod
    def _lance_row(record: VersionRecord) -> dict[str, object]:
        return asdict(record)


def create_export_version_record(
    *,
    version_id: str,
    dataset_id: str,
    description: str | None,
    filter_query: str | None,
    num_episodes: int,
    num_frames: int,
    export_format: str,
    export_uri: str | None,
    created_by: str = "local",
) -> VersionRecord:
    return VersionRecord(
        version_id=version_id,
        parent_version_id=None,
        dataset_id=dataset_id,
        description=description,
        filter_query=filter_query,
        num_episodes=num_episodes,
        num_frames=num_frames,
        export_format=export_format,
        export_uri=export_uri,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
    )


version_store = VersionStore()
