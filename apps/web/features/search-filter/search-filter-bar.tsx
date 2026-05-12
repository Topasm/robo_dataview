import { useState } from "react";
import { Plus, Save, Search, SlidersHorizontal, Trash2 } from "lucide-react";

import type { FilterPreset, SearchResult } from "@/lib/types";

type SearchFilterBarProps = {
  filterPresets: FilterPreset[];
  results: SearchResult[];
  onCreateFilterPreset: (name: string, query: string) => Promise<void>;
  onDeleteFilterPreset: (presetId: string) => Promise<void>;
  onFilterSearch: (query: string) => Promise<void>;
  onSelectResult: (episodeIndex: number) => void;
  onSemanticSearch: (text: string, filterQuery?: string) => Promise<void>;
};

type FilterValueType = "boolean" | "number" | "status" | "text";

type FilterField = {
  key: string;
  label: string;
  operators: FilterOperator[];
  valueType: FilterValueType;
};

type FilterOperator = "==" | "!=" | ">" | ">=" | "<" | "<=" | "contains";

type FilterRow = {
  id: string;
  field: string;
  operator: FilterOperator;
  value: string;
};

const FILTER_FIELDS: FilterField[] = [
  { key: "review_status", label: "Review", operators: ["==", "!=", "contains"], valueType: "status" },
  { key: "success_label", label: "Success", operators: ["==", "!="], valueType: "boolean" },
  { key: "quality_score", label: "Quality", operators: [">=", ">", "<=", "<", "==", "!="], valueType: "number" },
  { key: "task_index", label: "Task", operators: ["==", "!=", ">=", ">", "<=", "<"], valueType: "number" },
  { key: "episode_index", label: "Episode", operators: ["==", "!=", ">=", ">", "<=", "<"], valueType: "number" },
  { key: "instruction_text", label: "Instruction", operators: ["contains", "==", "!="], valueType: "text" },
  { key: "has_instruction", label: "Has Instruction", operators: ["==", "!="], valueType: "boolean" },
  { key: "has_wrist_camera", label: "Wrist Camera", operators: ["==", "!="], valueType: "boolean" },
  { key: "caption", label: "Caption", operators: ["contains", "==", "!="], valueType: "text" },
  { key: "split", label: "Split", operators: ["==", "!=", "contains"], valueType: "text" }
];

const BOOLEAN_OPTIONS = ["true", "false"];
const STATUS_OPTIONS = ["pending", "accepted", "rejected", "edited"];
const DEFAULT_FILTER_FIELD = FILTER_FIELDS[0];

export function SearchFilterBar({
  filterPresets,
  onCreateFilterPreset,
  onDeleteFilterPreset,
  onFilterSearch,
  results,
  onSelectResult,
  onSemanticSearch
}: SearchFilterBarProps) {
  const [semanticText, setSemanticText] = useState("");
  const [filterRows, setFilterRows] = useState<FilterRow[]>([
    {
      id: "filter-1",
      field: DEFAULT_FILTER_FIELD.key,
      operator: "==",
      value: "accepted"
    }
  ]);
  const [presetName, setPresetName] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const filterQuery = buildFilterQuery(filterRows);

  async function handleSearch() {
    // Smart-combine: when both the semantic text and a structured filter
    // are present, send them together (`semanticText` ∩ `filterQuery`);
    // otherwise the search degenerates to whichever side is filled.
    const text = semanticText.trim();
    if (!text) return;
    setIsSearching(true);
    try {
      await onSemanticSearch(text, filterQuery || undefined);
    } finally {
      setIsSearching(false);
    }
  }

  async function handleFilter() {
    if (!filterQuery) {
      return;
    }
    setIsSearching(true);
    try {
      await onFilterSearch(filterQuery);
    } finally {
      setIsSearching(false);
    }
  }

  function addFilterRow() {
    setFilterRows((current) => [
      ...current,
      {
        id: `filter-${Date.now()}`,
        field: DEFAULT_FILTER_FIELD.key,
        operator: "==",
        value: "accepted"
      }
    ]);
  }

  function removeFilterRow(rowId: string) {
    setFilterRows((current) => current.filter((row) => row.id !== rowId));
  }

  function updateFilterRow(rowId: string, patch: Partial<FilterRow>) {
    setFilterRows((current) =>
      current.map((row) => {
        if (row.id !== rowId) {
          return row;
        }
        const next = { ...row, ...patch };
        const field = fieldByKey(next.field);
        const operator = field.operators.includes(next.operator) ? next.operator : field.operators[0];
        return {
          ...next,
          operator,
          value: normalizeFilterValue(next.value, field.valueType)
        };
      })
    );
  }

  function applyPreset(presetId: string) {
    setSelectedPresetId(presetId);
    const preset = filterPresets.find((item) => item.presetId === presetId);
    if (preset) {
      setFilterRows(parseFilterQuery(preset.query));
      setPresetName(preset.name);
    }
  }

  async function savePreset() {
    const name = presetName.trim();
    if (!name || !filterQuery) {
      return;
    }
    setIsSearching(true);
    try {
      await onCreateFilterPreset(name, filterQuery);
      setPresetName("");
      setSelectedPresetId("");
    } finally {
      setIsSearching(false);
    }
  }

  async function deleteSelectedPreset() {
    if (!selectedPresetId) {
      return;
    }
    setIsSearching(true);
    try {
      await onDeleteFilterPreset(selectedPresetId);
      setSelectedPresetId("");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <section className="search-filter-bar">
      <div className="semantic-search-row">
        <div className="search-box">
          <Search size={16} />
          <input
            aria-label="Search episodes, labels, captions"
            onChange={(event) => setSemanticText(event.target.value)}
            placeholder="Search episodes, labels, captions..."
            value={semanticText}
          />
        </div>
        <button
          className="icon-button"
          disabled={isSearching || !semanticText.trim()}
          onClick={handleSearch}
          title={
            filterQuery
              ? "Search semantic text within the active filter"
              : "Semantic search"
          }
          type="button"
        >
          <Search size={16} />
        </button>
      </div>

      <details className="advanced-menu search-advanced-menu">
        <summary>Filters</summary>
        <div className="advanced-menu-content search-advanced-content">
          <div className="typed-filter-builder">
            <div className="filter-rows">
              {filterRows.map((row) => {
                const field = fieldByKey(row.field);
                return (
                  <div className="filter-row" key={row.id}>
                    <select
                      aria-label="Filter field"
                      onChange={(event) =>
                        updateFilterRow(row.id, {
                          field: event.target.value,
                          operator: fieldByKey(event.target.value).operators[0]
                        })
                      }
                      value={row.field}
                    >
                      {FILTER_FIELDS.map((option) => (
                        <option key={option.key} value={option.key}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Filter operator"
                      onChange={(event) =>
                        updateFilterRow(row.id, { operator: event.target.value as FilterOperator })
                      }
                      value={row.operator}
                    >
                      {field.operators.map((operator) => (
                        <option key={operator} value={operator}>
                          {operator}
                        </option>
                      ))}
                    </select>
                    <FilterValueInput
                      onChange={(value) => updateFilterRow(row.id, { value })}
                      type={field.valueType}
                      value={row.value}
                    />
                    <button
                      className="icon-button"
                      disabled={filterRows.length === 1}
                      onClick={() => removeFilterRow(row.id)}
                      title="Remove filter"
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="filter-actions">
              <button
                className="btn btn--sm btn--ghost"
                onClick={addFilterRow}
                title="Add another filter row"
                type="button"
              >
                <Plus size={14} />
                <span>Add filter</span>
              </button>
              <button
                className="btn btn--sm btn--primary"
                disabled={isSearching || !filterQuery}
                onClick={handleFilter}
                title="Apply the current filter to the episode list"
                type="button"
              >
                <SlidersHorizontal size={14} />
                <span>Apply filter</span>
              </button>
            </div>
          </div>

          {filterQuery ? <div className="filter-query-preview mono">{filterQuery}</div> : null}

          <div className="filter-preset-row">
            <select
              aria-label="Saved filter presets"
              onChange={(event) => applyPreset(event.target.value)}
              value={selectedPresetId}
            >
              <option value="">Saved filters</option>
              {filterPresets.map((preset) => (
                <option key={preset.presetId} value={preset.presetId}>
                  {preset.name}
                </option>
              ))}
            </select>
            <input
              aria-label="Filter preset name"
              onChange={(event) => setPresetName(event.target.value)}
              placeholder="Preset name"
              value={presetName}
            />
            <button
              className="icon-button"
              disabled={isSearching || !presetName.trim() || !filterQuery}
              onClick={savePreset}
              title="Save filter preset"
              type="button"
            >
              <Save size={15} />
            </button>
            <button
              className="icon-button"
              disabled={isSearching || !selectedPresetId}
              onClick={deleteSelectedPreset}
              title="Delete filter preset"
              type="button"
            >
              <Trash2 size={15} />
            </button>
          </div>
        </div>
      </details>

      {results.length > 0 ? (
        <div className="search-results">
          {results.map((result) => (
            <button
              className="search-result"
              key={`${result.episodeIndex}-${result.frameIndex ?? "episode"}-${result.label}`}
              onClick={() => onSelectResult(result.episodeIndex)}
              type="button"
            >
              <span className="mono">#{result.episodeIndex}</span>
              <span>{result.label}</span>
              <span>{result.score?.toFixed(2) ?? ""}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function parseFilterQuery(query: string): FilterRow[] {
  const rows = query
    .split(/\s+AND\s+/i)
    .map((clause, index) => parseFilterClause(clause, index))
    .filter((row): row is FilterRow => row !== null);
  return rows.length > 0
    ? rows
    : [
        {
          id: `filter-${Date.now()}`,
          field: DEFAULT_FILTER_FIELD.key,
          operator: "==",
          value: "accepted"
        }
      ];
}

function parseFilterClause(clause: string, index: number): FilterRow | null {
  const match = clause.match(/^\s*([A-Za-z_][\w.]*)\s*(contains|==|!=|>=|<=|>|<)\s*(.+?)\s*$/i);
  if (!match) {
    return null;
  }
  const [, fieldKey, operator, rawValue] = match;
  const field = fieldByKey(fieldKey);
  if (field.key !== fieldKey || !field.operators.includes(operator as FilterOperator)) {
    return null;
  }
  return {
    id: `filter-${Date.now()}-${index}`,
    field: field.key,
    operator: operator as FilterOperator,
    value: normalizeFilterValue(parseFilterValue(rawValue), field.valueType)
  };
}

function parseFilterValue(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function FilterValueInput({
  onChange,
  type,
  value
}: {
  onChange: (value: string) => void;
  type: FilterValueType;
  value: string;
}) {
  if (type === "boolean") {
    return (
      <select aria-label="Filter value" onChange={(event) => onChange(event.target.value)} value={value}>
        {BOOLEAN_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  if (type === "status") {
    return (
      <select aria-label="Filter value" onChange={(event) => onChange(event.target.value)} value={value}>
        {STATUS_OPTIONS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      aria-label="Filter value"
      onChange={(event) => onChange(event.target.value)}
      type={type === "number" ? "number" : "text"}
      value={value}
    />
  );
}

function buildFilterQuery(rows: FilterRow[]): string {
  return rows
    .map((row) => {
      const field = fieldByKey(row.field);
      const value = row.value.trim();
      if (!value) {
        return "";
      }
      return `${row.field} ${row.operator} ${formatFilterValue(value, field.valueType)}`;
    })
    .filter(Boolean)
    .join(" AND ");
}

function fieldByKey(key: string): FilterField {
  return FILTER_FIELDS.find((field) => field.key === key) ?? DEFAULT_FILTER_FIELD;
}

function formatFilterValue(value: string, type: FilterValueType): string {
  if (type === "boolean") {
    return value === "true" ? "true" : "false";
  }
  if (type === "number") {
    return value;
  }
  return JSON.stringify(value);
}

function normalizeFilterValue(value: string, type: FilterValueType): string {
  if (type === "boolean") {
    return BOOLEAN_OPTIONS.includes(value) ? value : BOOLEAN_OPTIONS[0];
  }
  if (type === "status") {
    return STATUS_OPTIONS.includes(value) ? value : STATUS_OPTIONS[0];
  }
  if (type === "number") {
    return Number.isFinite(Number(value)) ? value : "0";
  }
  return value;
}
