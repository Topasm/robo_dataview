"use client";

import { Archive, ClipboardCopy, History } from "lucide-react";
import { useMemo, useState } from "react";

import type { ExportRecord } from "@/lib/types";

type ExportHistoryProps = {
  exports: ExportRecord[];
};

function formatTimestamp(value: string | null): string {
  if (!value) return "unknown";
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return value;
  }
}

export function ExportHistory({ exports }: ExportHistoryProps) {
  const ordered = useMemo(
    () => [...exports].sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? "")),
    [exports]
  );
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (ordered.length === 0) {
    return (
      <details className="advanced-menu export-history-menu">
        <summary>
          <History size={14} aria-hidden="true" />
          <span>Past versions (0)</span>
        </summary>
        <div className="advanced-menu-content">
          <div className="empty-state compact-empty-state">
            No applied versions yet. The first apply will land in <code>data/exports/</code>.
          </div>
        </div>
      </details>
    );
  }

  function copyOutputUri(record: ExportRecord) {
    const value = record.outputUri ?? record.exportId;
    void navigator.clipboard
      ?.writeText(value)
      .then(() => {
        setCopiedId(record.exportId);
        window.setTimeout(() => setCopiedId(null), 1500);
      })
      .catch(() => {
        setCopiedId(null);
      });
  }

  return (
    <details className="advanced-menu export-history-menu">
      <summary>
        <History size={14} aria-hidden="true" />
        <span>Past versions ({ordered.length})</span>
      </summary>
      <div className="advanced-menu-content export-history-list">
        {ordered.map((record, index) => {
          const isLatest = index === 0;
          return (
            <div
              key={record.exportId}
              className={`export-history-row${isLatest ? " export-history-row--latest" : ""}`}
            >
              <div className="export-history-meta">
                <span className="export-history-time">
                  <Archive size={12} aria-hidden="true" />
                  {formatTimestamp(record.createdAt)}
                </span>
                <span className="muted mono">
                  {record.numEpisodes} ep · {record.format}
                  {isLatest ? " · current" : null}
                </span>
              </div>
              <div className="export-history-uri muted mono" title={record.outputUri ?? record.exportId}>
                {record.outputUri ?? record.exportId}
              </div>
              <button
                className="text-button compact-text-button"
                onClick={() => copyOutputUri(record)}
                title="Copy output path to clipboard"
                aria-label="Copy export output path"
                type="button"
              >
                <ClipboardCopy size={13} />
                {copiedId === record.exportId ? "Copied" : "Copy path"}
              </button>
            </div>
          );
        })}
      </div>
    </details>
  );
}
