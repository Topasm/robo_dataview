type StatusPillProps = {
  status: string;
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Need Check",
  accepted: "Keep",
  rejected: "Drop",
  edited: "Edited",
  ready: "Ready",
  error: "Error",
  warning: "Warning",
  succeeded: "Done",
  failed: "Failed",
  running: "Running",
};

export function StatusPill({ status }: StatusPillProps) {
  return (
    <span className={`status-pill status-${status}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
