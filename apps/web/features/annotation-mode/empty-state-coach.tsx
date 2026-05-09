"use client";

import { X } from "lucide-react";

type EmptyStateCoachProps = {
  onDismiss: () => void;
};

const STEPS: { kbd: string; text: string }[] = [
  { kbd: "Space", text: "Play the episode" },
  { kbd: "I", text: "Mark the start of a skill" },
  { kbd: "O", text: "Mark the end" },
  { kbd: "1–9", text: "Tap a skill key — clip is created and accepted in one stroke" }
];

// Note: STEPS[2].kbd is the letter "O" (mark out), not the digit "0" (which cancels draft).

export function EmptyStateCoach({ onDismiss }: EmptyStateCoachProps) {
  return (
    <div className="empty-coach-banner" role="note" aria-live="polite">
      <span className="empty-coach-banner-title">Cut your first skill clip:</span>
      <ol className="empty-coach-steps">
        {STEPS.map((step) => (
          <li key={step.text}>
            <kbd>{step.kbd}</kbd>
            <span>{step.text}</span>
          </li>
        ))}
      </ol>
      <span className="empty-coach-foot muted">
        Press <kbd>?</kbd> for the full cheatsheet.
      </span>
      <button
        type="button"
        className="icon-button empty-coach-dismiss"
        onClick={onDismiss}
        aria-label="Dismiss coaching tips"
        title="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  );
}
