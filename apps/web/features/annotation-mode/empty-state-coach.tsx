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
    <div className="empty-coach-overlay" aria-live="polite">
      <div className="empty-coach-card">
        <button
          type="button"
          className="empty-coach-dismiss icon-button"
          onClick={onDismiss}
          aria-label="Dismiss coaching tips"
          title="Dismiss"
        >
          <X size={14} />
        </button>
        <h2>Cut your first skill clip</h2>
        <ol className="empty-coach-steps">
          {STEPS.map((step) => (
            <li key={step.text}>
              <kbd>{step.kbd}</kbd>
              <span>{step.text}</span>
            </li>
          ))}
        </ol>
        <p className="empty-coach-foot">
          Press <kbd>?</kbd> any time for the full cheatsheet.
        </p>
      </div>
    </div>
  );
}
