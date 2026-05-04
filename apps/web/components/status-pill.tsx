type StatusPillProps = {
  status: string;
};

export function StatusPill({ status }: StatusPillProps) {
  return <span className={`status-pill status-${status}`}>{status}</span>;
}
