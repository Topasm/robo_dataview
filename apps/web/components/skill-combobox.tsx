"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Plus } from "lucide-react";

import { HUMANOID_SKILLS } from "@/lib/skill-vocabulary";
import {
  addCustomSkill,
  humanizeSkillName,
  removeCustomSkill,
  useCustomSkills
} from "@/lib/custom-skills";

type Item = {
  name: string;
  label: string;
  color: string;
  origin: "canonical" | "custom";
  id: number;
};

type SkillComboboxProps = {
  value: string;
  onChange: (name: string) => void;
  /** Show a small × on custom rows that lets the user remove them. */
  allowCustomRemoval?: boolean;
  placeholder?: string;
  /** Focus the input and pre-open the suggestion list on mount. Used in
   *  the hot bar's inline-add slot so a single click on `+` lands the
   *  user straight into typing with the canonical skills already listed. */
  autoFocus?: boolean;
  /** Optional callback when the user dismisses the combobox via Esc. */
  onCancel?: () => void;
};

export function SkillCombobox({
  value,
  onChange,
  allowCustomRemoval = true,
  placeholder = "Type to search or add…",
  autoFocus = false,
  onCancel
}: SkillComboboxProps) {
  const customSkills = useCustomSkills();
  const items: Item[] = useMemo(() => {
    const canonical: Item[] = HUMANOID_SKILLS.map((skill) => ({
      name: skill.name,
      label: skill.label,
      color: skill.color,
      origin: "canonical",
      id: skill.id
    }));
    const custom: Item[] = customSkills.map((skill) => ({
      name: skill.name,
      label: skill.label,
      color: skill.color,
      origin: "custom",
      id: -1
    }));
    return [...canonical, ...custom];
  }, [customSkills]);

  const selected = items.find((item) => item.name === value);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.label.toLowerCase().includes(q)
    );
  }, [items, query]);

  const trimmedQuery = query.trim();
  const normalizedQuery = trimmedQuery.toLowerCase().replace(/\s+/g, "_");
  const canAdd =
    trimmedQuery.length > 0 &&
    /^[a-z0-9][a-z0-9_-]*$/.test(normalizedQuery) &&
    !items.some((item) => item.name === normalizedQuery);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(event: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", onClickOutside);
    return () => window.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  useEffect(() => {
    if (autoFocus) {
      setOpen(true);
      // Defer to next tick so the input is mounted before focusing.
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
  }, [autoFocus]);

  function commitItem(item: Item) {
    onChange(item.name);
    setQuery("");
    setOpen(false);
    setHighlight(0);
  }

  function commitNew() {
    const created = addCustomSkill(trimmedQuery);
    if (!created) return;
    onChange(created.name);
    setQuery("");
    setOpen(false);
    setHighlight(0);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    const optionsCount = filtered.length + (canAdd ? 1 : 0);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setHighlight((current) =>
        optionsCount === 0 ? 0 : (current + 1) % optionsCount
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setHighlight((current) =>
        optionsCount === 0 ? 0 : (current - 1 + optionsCount) % optionsCount
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (highlight < filtered.length) {
        commitItem(filtered[highlight]);
      } else if (canAdd) {
        commitNew();
      }
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
      onCancel?.();
    }
  }

  return (
    <div className="skill-combobox" ref={wrapRef}>
      <div
        className={`skill-combobox-input${open ? " is-open" : ""}`}
        onClick={() => {
          inputRef.current?.focus();
          setOpen(true);
        }}
      >
        {selected && !open ? (
          <>
            <span
              className="skill-combobox-color"
              style={{ background: selected.color }}
              aria-hidden
            />
            <span className="skill-combobox-selected">
              {selected.origin === "canonical" ? `${selected.id}: ` : ""}
              {selected.label}
              {selected.origin === "custom" ? (
                <span className="muted"> · custom</span>
              ) : null}
            </span>
          </>
        ) : null}
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setHighlight(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={selected && !open ? "" : placeholder}
          aria-label="Skill"
          autoComplete="off"
          spellCheck={false}
        />
      </div>
      {open ? (
        <div className="skill-combobox-popover" role="listbox">
          {filtered.length === 0 && !canAdd ? (
            <div className="skill-combobox-empty muted">No matches</div>
          ) : null}
          {filtered.map((item, idx) => {
            const active = idx === highlight;
            const isSelected = item.name === value;
            return (
              <button
                key={item.name}
                type="button"
                role="option"
                aria-selected={isSelected}
                className={`skill-combobox-row${active ? " is-active" : ""}${isSelected ? " is-selected" : ""}`}
                onClick={() => commitItem(item)}
                onMouseEnter={() => setHighlight(idx)}
              >
                <span
                  className="skill-combobox-color"
                  style={{ background: item.color }}
                  aria-hidden
                />
                <span className="skill-combobox-name">
                  {item.origin === "canonical" ? `${item.id}: ` : ""}
                  {item.label}
                </span>
                <span className="skill-combobox-meta muted">
                  {item.origin === "custom" ? "custom" : item.name}
                </span>
                {item.origin === "custom" && allowCustomRemoval ? (
                  <span
                    className="skill-combobox-remove"
                    role="button"
                    tabIndex={-1}
                    aria-label={`Remove custom skill ${item.name}`}
                    title="Remove custom skill"
                    onClick={(event) => {
                      event.stopPropagation();
                      removeCustomSkill(item.name);
                    }}
                  >
                    ×
                  </span>
                ) : null}
              </button>
            );
          })}
          {canAdd ? (
            <button
              key="__add__"
              type="button"
              role="option"
              aria-selected={false}
              className={`skill-combobox-row skill-combobox-add${highlight === filtered.length ? " is-active" : ""}`}
              onClick={commitNew}
              onMouseEnter={() => setHighlight(filtered.length)}
            >
              <span className="skill-combobox-color skill-combobox-color-empty" aria-hidden>
                <Plus size={10} />
              </span>
              <span className="skill-combobox-name">
                Add &ldquo;{normalizedQuery}&rdquo;
              </span>
              <span className="skill-combobox-meta muted">
                {humanizeSkillName(normalizedQuery)}
              </span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
