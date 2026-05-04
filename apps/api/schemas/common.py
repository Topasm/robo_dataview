from enum import Enum


class ReviewStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"


class AnnotationSource(str, Enum):
    human = "human"
    vlm = "vlm"
    heuristic = "heuristic"
    import_ = "import"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ExportFormat(str, Enum):
    lerobot = "lerobot"
    hf_dataset = "hf_dataset"
    lance = "lance"
    jsonl = "jsonl"
    vla = "vla"
