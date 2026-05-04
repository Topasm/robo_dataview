import { useState } from "react";
import { Plus, Search, SlidersHorizontal, Trash2 } from "lucide-react";

import type { SearchResult } from "@/lib/types";

type SearchFilterBarProps = {
  results: SearchResult[];
  onFilterSearch: (query: string) => Promise<void>;
  onSelectResult: (episodeIndex: number) => void;
  onSemanticSearch: (text: string) => Promise<void>;
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
  { key: "caption", label: "Caption", operators: ["contains", "==", "!="], valueType: "text" },
  { key: "split", label: "Split", operators: ["==", "!=", "contains"], valueType: "text" }
];

const BOOLEAN_OPTIONS = ["true", "false"];
const STATUS_OPTIONS = ["pending", "accepted", "rejected", "edited"];
const DEFAULT_FILTER_FIELD = FILTER_FIELDS[0];

export function SearchFilterBar({
  onFilterSearch,
  results,
  onSelectResult,
  onSemanticSearch
}: SearchFilterBarProps) {
  const [semanticText, setSemanticText] = useState("cloth edge grasp");
  const [filterRows, setFilterRows] = useState<FilterRow[]>([
    {
      id: "filter-1",
      field: DEFAULT_FILTER_FIELD.key,
      operator: "==",
      value: "accepted"
    }
  ]);
  const [isSearching, setIsSearching] = useState(false);
  const filterQuery = buildFilterQuery(filterRows);

  async function handleSearch() {
    if (!semanticText.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      await onSemanticSearch(semanticText.trim());
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

  return (
    <section className="search-filter-bar">
      <div className="semantic-search-row">
        <div className="search-box">
          <Search size={16} />
          <input
            aria-label="Semantic search text"
            onChange={(event) => setSemanticText(event.target.value)}
            value={semanticText}
          />
        </div>
        <button
          className="icon-button"
          disabled={isSearching || !semanticText.trim()}
          onClick={handleSearch}
          title="Semantic search"
          type="button"
        >
          <Search size={16} />
        </button>
      </div>

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
          <button className="icon-button" onClick={addFilterRow} title="Add filter" type="button">
            <Plus size={15} />
          </button>
          <button
            className="icon-button"
            disabled={isSearching || !filterQuery}
            onClick={handleFilter}
            title="Episode filter"
            type="button"
          >
            <SlidersHorizontal size={16} />
          </button>
        </div>
      </div>

      {filterQuery ? <div className="filter-query-preview mono">{filterQuery}</div> : null}

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
