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
  /** Per-dimension state values (only when stateDim > 0 and small enough to chart inline). */
  [key: `s${number}`]: number | null | undefined;
  [key: `a${number}`]: number | null | undefined;
};

const STATE_COLOR = "var(--accent)";
const ACTION_COLOR = "var(--blue)";
const MAX_DIMS_INLINE = 6;

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

  const data = useMemo<ChartRow[]>(() => {
    if (!timeseries) return [];
    const stateDim = Math.min(timeseries.stateDim ?? 0, MAX_DIMS_INLINE);
    const actionDim = Math.min(timeseries.actionDim ?? 0, MAX_DIMS_INLINE);
    return timeseries.sampleIndices.map((frame, sampleIdx) => {
      const row: ChartRow = {
        frame,
        state: timeseries.stateNorms[sampleIdx] ?? null,
        action: timeseries.actionNorms[sampleIdx] ?? null
      };
      const stateVec = timeseries.stateValues[sampleIdx];
      if (stateVec) {
        for (let d = 0; d < stateDim; d++) {
          row[`s${d}` as const] = stateVec[d] ?? null;
        }
      }
      const actionVec = timeseries.actionValues[sampleIdx];
      if (actionVec) {
        for (let d = 0; d < actionDim; d++) {
          row[`a${d}` as const] = actionVec[d] ?? null;
        }
      }
      return row;
    });
  }, [timeseries]);

  // Skill clip overlays — accepted clips become colored ReferenceArea bands.
  const skillBands = useMemo(
    () =>
      annotations
        .filter(
          (row) =>
            row.datasetId === episode.datasetId &&
            row.episodeIndex === episode.episodeIndex &&
            row.labelType === SKILL_LABEL_TYPE &&
            row.reviewStatus === "accepted"
        )
        .map((row) => {
          const skill = skillByName(row.labelValue);
          return {
            id: row.id,
            startFrame: row.startFrame,
            endFrame: row.endFrame,
            skillName: row.labelValue,
            color: skill?.color ?? "var(--muted)"
          };
        }),
    [annotations, episode.datasetId, episode.episodeIndex]
  );

  const lastFrame = Math.max(0, episode.length - 1);
  const stateDim = Math.min(timeseries?.stateDim ?? 0, MAX_DIMS_INLINE);
  const actionDim = Math.min(timeseries?.actionDim ?? 0, MAX_DIMS_INLINE);
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

  return (
    <div className={`episode-charts variant-${variant}`}>
      <ChartCard
        title="State"
        chartHeight={chartHeight}
        data={data}
        seriesKey="state"
        seriesColor={STATE_COLOR}
        dimSeries={Array.from({ length: stateDim }, (_, d) => ({
          key: `s${d}`,
          color: dimColor(d)
        }))}
        skillBands={skillBands}
        currentFrame={selectedFrame}
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
        dimSeries={Array.from({ length: actionDim }, (_, d) => ({
          key: `a${d}`,
          color: dimColor(d)
        }))}
        skillBands={skillBands}
        currentFrame={selectedFrame}
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
};

type DimSeries = { key: string; color: string };

function ChartCard({
  title,
  chartHeight,
  data,
  seriesKey,
  seriesColor,
  dimSeries,
  skillBands,
  currentFrame,
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
  lastFrame: number;
  onClick: (payload: { activeLabel?: string | number } | null) => void;
  onMove?: (payload: { activeLabel?: string | number } | null) => void;
}) {
  return (
    <section className="episode-chart-card">
      <header className="episode-chart-card-header">
        <span className="episode-chart-card-title">{title}</span>
        <span className="muted episode-chart-card-meta">
          {dimSeries.length > 0 ? `${dimSeries.length} dims + norm` : "norm"}
        </span>
      </header>
      <div style={{ width: "100%", height: chartHeight }}>
        <ResponsiveContainer>
          <LineChart
            data={data}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
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
              width={28}
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
            />

            {/* Skill clip background bands */}
            {skillBands.map((band) => (
              <ReferenceArea
                key={band.id}
                x1={band.startFrame}
                x2={band.endFrame}
                fill={band.color}
                fillOpacity={0.12}
                stroke="none"
                ifOverflow="hidden"
              />
            ))}

            {/* Per-dim faint lines first */}
            {dimSeries.map((dim) => (
              <Line
                key={dim.key}
                type="monotone"
                dataKey={dim.key}
                stroke={dim.color}
                strokeOpacity={0.55}
                strokeWidth={1}
                dot={false}
                isAnimationActive={false}
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
            />

            {/* Playhead */}
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
    </section>
  );
}

const DIM_PALETTE = [
  "#f97316",
  "#3b82f6",
  "#22c55e",
  "#a855f7",
  "#ec4899",
  "#14b8a6"
];

function dimColor(index: number): string {
  return DIM_PALETTE[index % DIM_PALETTE.length] ?? "var(--muted)";
}
