"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { fetchEpisodeTimeseries } from "@/lib/api";
import { skillByName, SKILL_LABEL_TYPE } from "@/lib/skill-vocabulary";
import type { Episode, EpisodeTimeseries, SegmentAnnotation } from "@/lib/types";

type EpisodeChartsProps = {
  episode: Episode;
  annotations: SegmentAnnotation[];
  selectedFrame: number;
  onSelectFrame?: (frame: number) => void;
  /** "compact" trims chart heights for use inside Annotate mode beside the timeline. */
  variant?: "default" | "compact";
  /** When true, hovering along a chart updates the global frame index (camera + HUD follow). */
  hoverSeek?: boolean;
};

type ChartRow = {
  frame: number;
  state: number | null;
  action: number | null;
  // Per-dimension state/action values, keyed by series id (s0/a0 fallback or
  // joint name when info.json/manifest provides one).
  [key: string]: number | null | string | undefined;
};

const STATE_COLOR = "var(--accent)";
const ACTION_COLOR = "var(--blue)";
const MAX_DIMS_INLINE = 32;
const CHART_LEFT_GUTTER = 64;
const CHART_Y_AXIS_WIDTH = 28;

export function EpisodeCharts({
  episode,
  annotations,
  selectedFrame,
  onSelectFrame,
  variant = "default",
  hoverSeek = true
}: EpisodeChartsProps) {
  const [timeseries, setTimeseries] = useState<EpisodeTimeseries | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setTimeseries(null);
    setStatus("loading");
    fetchEpisodeTimeseries(episode.datasetId, episode.episodeIndex)
      .then((next) => {
        if (cancelled) return;
        setTimeseries(next);
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [episode.datasetId, episode.episodeIndex]);

  const stateDim = Math.min(timeseries?.stateDim ?? 0, MAX_DIMS_INLINE);
  const actionDim = Math.min(timeseries?.actionDim ?? 0, MAX_DIMS_INLINE);

  const stateSeries = useMemo<DimSeries[]>(
    () => buildDimSeries(stateDim, timeseries?.stateNames ?? null, "s"),
    [stateDim, timeseries?.stateNames]
  );
  const actionSeries = useMemo<DimSeries[]>(
    () => buildDimSeries(actionDim, timeseries?.actionNames ?? null, "a"),
    [actionDim, timeseries?.actionNames]
  );

  const data = useMemo<ChartRow[]>(() => {
    if (!timeseries) return [];
    return timeseries.sampleIndices.map((frame, sampleIdx) => {
      const row: ChartRow = {
        frame,
        state: timeseries.stateNorms[sampleIdx] ?? null,
        action: timeseries.actionNorms[sampleIdx] ?? null
      };
      const stateVec = timeseries.stateValues[sampleIdx];
      if (stateVec) {
        for (let d = 0; d < stateDim; d++) {
          row[stateSeries[d].key] = stateVec[d] ?? null;
        }
      }
      const actionVec = timeseries.actionValues[sampleIdx];
      if (actionVec) {
        for (let d = 0; d < actionDim; d++) {
          row[actionSeries[d].key] = actionVec[d] ?? null;
        }
      }
      return row;
    });
  }, [timeseries, stateDim, actionDim, stateSeries, actionSeries]);

  const skillBands = useMemo(
    () =>
      annotations
        .filter(
          (row) =>
            row.datasetId === episode.datasetId &&
            row.episodeIndex === episode.episodeIndex &&
            row.labelType === SKILL_LABEL_TYPE &&
            row.reviewStatus !== "rejected"
        )
        .map((row) => {
          const skill = skillByName(row.labelValue);
          return {
            id: row.id,
            startFrame: row.startFrame,
            endFrame: row.endFrame,
            skillName: row.labelValue,
            color: skill?.color ?? "var(--muted)",
            reviewStatus: row.reviewStatus
          };
        }),
    [annotations, episode.datasetId, episode.episodeIndex]
  );

  const lastFrame = Math.max(0, episode.length - 1);
  const chartHeight = variant === "compact" ? 96 : 132;

  if (status === "loading") {
    return (
      <div className="episode-charts episode-charts-empty">
        <span className="muted">Loading state / action timeseries…</span>
      </div>
    );
  }
  if (status === "error" || data.length === 0) {
    return (
      <div className="episode-charts episode-charts-empty">
        <span className="muted">Timeseries unavailable for this episode.</span>
      </div>
    );
  }

  function seekFromPayload(payload: { activeLabel?: string | number } | null) {
    if (!onSelectFrame || !payload) return;
    const v = payload.activeLabel;
    if (v == null) return;
    const frame = typeof v === "number" ? v : Number(v);
    if (!Number.isFinite(frame)) return;
    const clamped = Math.max(0, Math.min(lastFrame, Math.round(frame)));
    if (clamped !== selectedFrame) {
      onSelectFrame(clamped);
    }
  }

  const handleClick = seekFromPayload;
  const handleMove = hoverSeek ? seekFromPayload : undefined;

  // Pick the row closest to selectedFrame for the live legend value column.
  const closestRow = data.length > 0 ? closestRowFor(data, selectedFrame) : null;

  return (
    <div className={`episode-charts variant-${variant}`}>
      <ChartCard
        title="State"
        chartHeight={chartHeight}
        data={data}
        seriesKey="state"
        seriesColor={STATE_COLOR}
        dimSeries={stateSeries}
        skillBands={skillBands}
        currentFrame={selectedFrame}
        currentRow={closestRow}
        lastFrame={lastFrame}
        onClick={handleClick}
        onMove={handleMove}
      />
      <ChartCard
        title="Action"
        chartHeight={chartHeight}
        data={data}
        seriesKey="action"
        seriesColor={ACTION_COLOR}
        dimSeries={actionSeries}
        skillBands={skillBands}
        currentFrame={selectedFrame}
        currentRow={closestRow}
        lastFrame={lastFrame}
        onClick={handleClick}
        onMove={handleMove}
      />
    </div>
  );
}

type SkillBand = {
  id: string;
  startFrame: number;
  endFrame: number;
  skillName: string;
  color: string;
  reviewStatus: SegmentAnnotation["reviewStatus"];
};

type DimSeries = {
  key: string;
  label: string;
  group: string;
  color: string;
};

function ChartCard({
  title,
  chartHeight,
  data,
  seriesKey,
  seriesColor,
  dimSeries,
  skillBands,
  currentFrame,
  currentRow,
  lastFrame,
  onClick,
  onMove
}: {
  title: string;
  chartHeight: number;
  data: ChartRow[];
  seriesKey: "state" | "action";
  seriesColor: string;
  dimSeries: DimSeries[];
  skillBands: SkillBand[];
  currentFrame: number;
  currentRow: ChartRow | null;
  lastFrame: number;
  onClick: (payload: { activeLabel?: string | number } | null) => void;
  onMove?: (payload: { activeLabel?: string | number } | null) => void;
}) {
  const [fullscreen, setFullscreen] = useState(false);

  // Per-chart visibility state (persisted in localStorage). Default: no
  // per-joint overlays, so the norm trace stays readable in tight workspaces.
  const storageKey = `rds.chart.visibleKeys.v2.${seriesKey}`;
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(
    () => new Set()
  );
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(storageKey);
    if (stored !== null) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setVisibleKeys(new Set(parsed.map(String)));
        }
      } catch {
        /* ignore corrupt entry */
      }
    }
    setHydrated(true);
  }, [storageKey]);
  useEffect(() => {
    if (!hydrated || typeof window === "undefined") return;
    window.localStorage.setItem(storageKey, JSON.stringify([...visibleKeys]));
  }, [storageKey, visibleKeys, hydrated]);

  const [showLegend, setShowLegend] = useState(false);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setFullscreen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [fullscreen]);

  const containerHeight = fullscreen ? "calc(100vh - 88px)" : chartHeight;

  // Group dims by their `group` field so legend can render group headers.
  const grouped = useMemo(() => groupDimSeries(dimSeries), [dimSeries]);
  const visibleDimSeries = dimSeries.filter((d) => visibleKeys.has(d.key));

  function toggleKey(key: string) {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function setGroup(group: string, on: boolean) {
    const groupKeys = grouped.groups[group]?.map((d) => d.key) ?? [];
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      for (const key of groupKeys) {
        if (on) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }

  function setAll(on: boolean) {
    setVisibleKeys(on ? new Set(dimSeries.map((dim) => dim.key)) : new Set());
  }

  return (
    <section
      className={`episode-chart-card${fullscreen ? " is-fullscreen" : ""}`}
    >
      <header className="episode-chart-card-header">
        <span className="episode-chart-card-title">{title}</span>
        <span className="muted episode-chart-card-meta">
          {dimSeries.length > 0 ? `${dimSeries.length} dims + norm` : "norm"}
        </span>
        {dimSeries.length > 0 ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => setShowLegend((v) => !v)}
            aria-pressed={showLegend}
            title={showLegend ? "Hide joint series controls" : "Show joint series controls"}
          >
            {showLegend ? "Hide joints" : "Show joints"}
          </button>
        ) : null}
        <button
          type="button"
          className="btn btn--icon episode-chart-fullscreen-btn"
          onClick={() => setFullscreen((value) => !value)}
          title={fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
          aria-label={fullscreen ? "Exit fullscreen" : "Open chart fullscreen"}
        >
          {fullscreen ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M8 3v3a2 2 0 0 1-2 2H3" />
              <path d="M21 8h-3a2 2 0 0 1-2-2V3" />
              <path d="M3 16h3a2 2 0 0 1 2 2v3" />
              <path d="M16 21v-3a2 2 0 0 1 2-2h3" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M3 8V3h5" />
              <path d="M21 8V3h-5" />
              <path d="M3 16v5h5" />
              <path d="M21 16v5h-5" />
            </svg>
          )}
        </button>
      </header>
      <div style={{ width: "100%", height: containerHeight }}>
        <ResponsiveContainer>
          <LineChart
            data={data}
            margin={{ top: 4, right: 0, left: CHART_LEFT_GUTTER, bottom: 0 }}
            onClick={onClick}
            onMouseMove={onMove}
          >
            <CartesianGrid stroke="var(--border)" strokeDasharray="2 2" vertical={false} />
            <XAxis
              dataKey="frame"
              type="number"
              domain={[0, lastFrame]}
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              minTickGap={24}
            />
            <YAxis
              tickLine={false}
              axisLine={{ stroke: "var(--border)" }}
              tick={{ fill: "var(--muted)", fontSize: 10 }}
              width={CHART_Y_AXIS_WIDTH}
            />
            <Tooltip
              cursor={{ stroke: "var(--accent)", strokeWidth: 1 }}
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                fontSize: 11,
                padding: "4px 8px"
              }}
              labelFormatter={(label) => `frame ${label}`}
              formatter={(value, name) => {
                const series = dimSeries.find((d) => d.key === name);
                return [value, series?.label ?? name];
              }}
            />

            {/* Skill clip background bands */}
            {skillBands.map((band) => {
              const isPending = band.reviewStatus === "pending";
              return (
                <ReferenceArea
                  key={band.id}
                  x1={band.startFrame}
                  x2={band.endFrame}
                  fill={band.color}
                  fillOpacity={isPending ? 0.09 : 0.15}
                  stroke={band.color}
                  strokeDasharray={isPending ? "4 3" : undefined}
                  strokeOpacity={isPending ? 0.24 : 0.34}
                  ifOverflow="hidden"
                />
              );
            })}

            {/* Per-dim faint lines (only those toggled visible) */}
            {visibleDimSeries.map((dim) => (
              <Line
                key={dim.key}
                type="monotone"
                dataKey={dim.key}
                stroke={dim.color}
                strokeOpacity={0.6}
                strokeWidth={1}
                dot={false}
                isAnimationActive={false}
                name={dim.label}
              />
            ))}

            {/* Norm line on top */}
            <Line
              type="monotone"
              dataKey={seriesKey}
              stroke={seriesColor}
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
              name="norm"
            />

            <ReferenceLine
              x={currentFrame}
              stroke="var(--accent)"
              strokeDasharray="3 2"
              strokeWidth={1.5}
              ifOverflow="extendDomain"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {showLegend && dimSeries.length > 0 ? (
        <ChartLegend
          grouped={grouped}
          visibleKeys={visibleKeys}
          currentRow={currentRow}
          onToggleKey={toggleKey}
          onSetGroup={setGroup}
          onSetAll={setAll}
        />
      ) : null}
    </section>
  );
}

function ChartLegend({
  grouped,
  visibleKeys,
  currentRow,
  onToggleKey,
  onSetGroup,
  onSetAll
}: {
  grouped: { groups: Record<string, DimSeries[]>; singles: DimSeries[] };
  visibleKeys: Set<string>;
  currentRow: ChartRow | null;
  onToggleKey: (key: string) => void;
  onSetGroup: (group: string, on: boolean) => void;
  onSetAll: (on: boolean) => void;
}) {
  const groupNames = Object.keys(grouped.groups);
  return (
    <div className="chart-legend">
      <div className="chart-legend-actions">
        <button className="btn btn--ghost btn--sm" type="button" onClick={() => onSetAll(true)}>
          All
        </button>
        <button className="btn btn--ghost btn--sm" type="button" onClick={() => onSetAll(false)}>
          Clear
        </button>
      </div>
      {groupNames.map((groupName) => {
        const members = grouped.groups[groupName];
        const allOn = members.every((d) => visibleKeys.has(d.key));
        const someOn = members.some((d) => visibleKeys.has(d.key));
        const groupColor = members[0].color;
        return (
          <div key={groupName} className="chart-legend-group">
            <label className="chart-legend-group-header">
              <input
                type="checkbox"
                checked={allOn}
                ref={(el) => {
                  if (el) el.indeterminate = someOn && !allOn;
                }}
                onChange={() => onSetGroup(groupName, !allOn)}
                style={{ accentColor: groupColor }}
              />
              <span className="chart-legend-group-name">{groupLabel(groupName)}</span>
            </label>
            <div className="chart-legend-members">
              {members.map((dim) => (
                <ChartLegendRow
                  key={dim.key}
                  dim={dim}
                  visible={visibleKeys.has(dim.key)}
                  value={currentRow?.[dim.key] as number | null | undefined}
                  onToggle={() => onToggleKey(dim.key)}
                />
              ))}
            </div>
          </div>
        );
      })}
      {grouped.singles.length > 0 ? (
        <div className="chart-legend-group">
          <div className="chart-legend-members">
            {grouped.singles.map((dim) => (
              <ChartLegendRow
                key={dim.key}
                dim={dim}
                visible={visibleKeys.has(dim.key)}
                value={currentRow?.[dim.key] as number | null | undefined}
                onToggle={() => onToggleKey(dim.key)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ChartLegendRow({
  dim,
  visible,
  value,
  onToggle
}: {
  dim: DimSeries;
  visible: boolean;
  value: number | null | undefined;
  onToggle: () => void;
}) {
  const formatted = typeof value === "number" ? value.toFixed(3) : "—";
  return (
    <label className={`chart-legend-row${visible ? "" : " is-hidden"}`}>
      <input
        type="checkbox"
        checked={visible}
        onChange={onToggle}
        style={{ accentColor: dim.color }}
      />
      <span className="chart-legend-name" title={dim.key}>
        {dim.label}
      </span>
      <span className="chart-legend-value mono">{formatted}</span>
    </label>
  );
}

function buildDimSeries(
  dim: number,
  names: string[] | null,
  fallback: "s" | "a"
): DimSeries[] {
  return Array.from({ length: dim }, (_, d) => {
    const name = names && names.length === dim ? names[d] : `${fallback}${d}`;
    const group = groupOf(name);
    return {
      key: name,
      label: shortLabel(name, group),
      group,
      color: groupColor(group, d)
    };
  });
}

function groupOf(name: string): string {
  // Match e.g. "arm_l_joint1" → "arm_l", "head_joint2" → "head",
  // "lift_joint" → "lift", "gripper_l_joint1" → "gripper_l".
  const m = name.match(/^(.+?)_(?:joint\d*|gripper\d*)$/i);
  if (m) return m[1];
  // Fallback: use everything before the last underscore as the group.
  const idx = name.lastIndexOf("_");
  if (idx > 0) return name.slice(0, idx);
  return "—";
}

const GROUP_LABELS: Record<string, string> = {
  arm_l: "Left Arm",
  arm_r: "Right Arm",
  gripper_l: "Left Gripper",
  gripper_r: "Right Gripper",
  head: "Head",
  lift: "Lift"
};

const KEEP_SINGLE_MEMBER_GROUPS = new Set(["gripper_l", "gripper_r", "head", "lift"]);

function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group;
}

function shortLabel(name: string, group: string): string {
  if (group === "—") return name;
  if (name.startsWith(`${group}_`)) return name.slice(group.length + 1);
  return name;
}

const GROUP_PALETTE: Record<string, string> = {
  arm_l: "#3b82f6",
  arm_r: "#22c55e",
  head: "#f97316",
  lift: "#a855f7",
  gripper_l: "#ec4899",
  gripper_r: "#14b8a6"
};

const FALLBACK_PALETTE = [
  "#f97316",
  "#3b82f6",
  "#22c55e",
  "#a855f7",
  "#ec4899",
  "#14b8a6",
  "#eab308",
  "#06b6d4"
];

function groupColor(group: string, fallbackIndex: number): string {
  return (
    GROUP_PALETTE[group] ??
    FALLBACK_PALETTE[fallbackIndex % FALLBACK_PALETTE.length] ??
    "var(--muted)"
  );
}

function groupDimSeries(dims: DimSeries[]): {
  groups: Record<string, DimSeries[]>;
  singles: DimSeries[];
} {
  const groups: Record<string, DimSeries[]> = {};
  for (const dim of dims) {
    if (!groups[dim.group]) groups[dim.group] = [];
    groups[dim.group].push(dim);
  }
  // Pull groups with only one member out into "singles" so the legend layout
  // doesn't show a one-row group header.
  const singles: DimSeries[] = [];
  for (const [name, members] of Object.entries(groups)) {
    if (members.length <= 1 && !KEEP_SINGLE_MEMBER_GROUPS.has(name)) {
      singles.push(...members);
      delete groups[name];
    }
  }
  return { groups, singles };
}

function closestRowFor(rows: ChartRow[], frame: number): ChartRow {
  // Rows are sample-spaced — pick the one with the smallest abs frame
  // distance.
  let best = rows[0];
  let bestDist = Math.abs((rows[0].frame as number) - frame);
  for (let i = 1; i < rows.length; i++) {
    const d = Math.abs((rows[i].frame as number) - frame);
    if (d < bestDist) {
      best = rows[i];
      bestDist = d;
    }
  }
  return best;
}
