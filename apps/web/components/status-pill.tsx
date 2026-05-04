import type { ReviewStatus } from "@/lib/types";

type StatusPillProps = {
  status: ReviewStatus | "sample" | "registered" | "queued" | "ready";
};

export function StatusPill({ status }: StatusPillProps) {
  return <span className={`status-pill status-${status}`}>{status}</span>;
}
