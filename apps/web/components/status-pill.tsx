type StatusPillProps = {
  status: string;
};

const STATUS_LABELS: Record<string, string> = {
  pending: "New",
  accepted: "Keep",
  rejected: "Drop",
  edited: "Edited",
  ready: "Ready",
  error: "Error",
  warning: "Warn",
  succeeded: "Done",
  failed: "Failed",
  running: "Run",
};

export function StatusPill({ status }: StatusPillProps) {
  return (
    <span className={`status-pill status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
