"""Worker entry point for VLM auto-labeling.

Phase 5 will connect this module to RQ or Celery, sample episode frames from
Lance, run the configured VLM, and write pending annotations.
"""


def main() -> None:
    raise SystemExit("VLM worker is not implemented yet.")


if __name__ == "__main__":
    main()
