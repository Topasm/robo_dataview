# UI Wireframe

Robot Data Studio uses a dense operations layout. The first screen is the tool
itself, not a marketing page.

```text
+----------------------------------------------------------------+
| Top Bar                                                        |
| Dataset | Task | Search | VLM Jobs | Export | Settings         |
+------------------+---------------------------------------------+
| Left Panel       | Main Viewer                                 |
|                  |                                             |
| Dataset Tree     | +-----------------------------------------+ |
| Episode List     | | Video Viewer / Rerun Web Viewer         | |
| Filters          | | multi-camera + state/action timeline    | |
| Status           | +-----------------------------------------+ |
+------------------+---------------------------------------------+
| Bottom Panel                                                   |
| timeline, phase segments, event markers, frame scrubber         |
+----------------------------------------------------------------+
| Right Panel                                                    |
| annotation editor, VLM outputs, metadata, export selection      |
+----------------------------------------------------------------+
```

## Primary Screens

### Dataset Browser

- Dataset open control
- Dataset summary
- Task list
- Episode count
- Frame count
- Camera count
- Review progress

### Episode List

Columns:

```text
episode_index
task_index
length
success_label
quality_score
review_status
caption
has_vlm_label
has_human_label
split
```

Actions:

```text
sort
filter
multi-select
batch label
batch export
batch run VLM
```

### Main Viewer

Modes:

```text
Lightweight video viewer
Rerun Web Viewer
```

The lightweight viewer is the default for fast review. Rerun is used when
precise replay, synchronized plots, or 3D visualization are needed.

### Timeline

Timeline content:

```text
frame index
timestamp
phase segments
VLM-proposed labels
human-confirmed labels
state/action norm
failure events
important frames
```

Editing actions:

```text
click frame
drag segment
split phase
merge phase
mark bad range
mark success/failure
```

### Annotation Editor

Episode-level fields:

```text
instruction
episode_caption
success/failure
failure_reason
quality_score
review_status
notes
```

Segment-level fields:

```text
phase label
start_frame
end_frame
confidence
source
```

Frame-level fields:

```text
object_visible
gripper_contact
bad_frame
occlusion
important_frame
```

## Current UI Implementation

Browse mode now uses a 3-column resizable shell (`<PanelGroup>` from
`react-resizable-panels`, autoSaveId `rds.browse.layout-3col`):

- **Left**: `DatasetBrowser` (datasets switcher list + URI open form) →
  `EpisodeList` (per-row Flag-with-memo and Delete↔Undo, no Quality column,
  Status pill compressed) → sidebar footer with `Annotate this episode →`
  (primary teal) and `Apply` (default outlined). Disposition panel and the
  legacy "Kept" filter were retired together with the explicit `kept` state.
- **Center**: `EpisodeViewer` (`stack` layout: cam_head + wrist row, each
  tile has a Maximize2 button to enlarge that camera viewport-wide) →
  `EpisodeCharts` with named joint series, live legend, group-by-prefix
  checkboxes (arm_l_*, arm_r_*, head_*, lift_*, gripper_*), and a
  Show/Hide series toggle → thin actions row with episode meta on the
  left and the strict-triage overlay toggle on the right.
- **Right**: `DatasetMeta` inspector — Dataset Progress + Advanced Details
  (URI, Episodes/Frames/FPS/Cameras metrics, Health, Cameras chips).

Annotate mode keeps the IconRail | center | inspector layout, with:

- IconRail buttons for Episodes / Search / Rerun / Apply (Download icon)
- `SkillHotBar` with canonical 0–9 chips, custom-skill chips (with × to
  remove), and a `+` button that opens a `SkillCombobox` autocomplete
  inline (search canonical + custom, or "Add 'xxx'" to register a new
  custom name into localStorage)
- `EmptyStateCoach` is a horizontal banner above the videos (was a
  floating overlay; moved out of `annotation-stage-preview` so it never
  covers the focus video)
- `AnnotationEditor` New Skill Clip form is just Start / End / Add Clip;
  skill identity reads from the hot bar so there is no duplicate picker

Other implemented panels:

- Top navigation shell with Browse/Annotate tabs, DirtyChip, Settings;
  banner is a `<select>` dataset switcher when more than one summary is
  registered.
- Search/filter bar with semantic text search, typed structured filter
  rows, and saved presets.
- Timeline panel showing segment annotations.
- Rerun panel that can request a backend session, link the generated
  `.rrd`, and embed ready recordings through the Rerun React viewer.
- Annotation editor (Clip / Frame / Coverage tabs) with create / update /
  delete / review actions and midpoint split.
- Export modal.

Current behavior:

- The UI loads API datasets first and falls back to sample data when the
  API is unavailable.
- UI state and API orchestration live in `apps/web/lib/use-studio-data.ts`.
- API adapters live in `apps/web/lib/api.ts`.
- Custom (user-defined) skills live in `apps/web/lib/custom-skills.ts`
  (localStorage); `skillByName` falls back to that registry. Exporting a
  Lance Training Bundle still rejects non-canonical labels per the
  `Skill vocabulary contract` in CLAUDE.md.

Missing UX:

- Simultaneous multi-camera layout and synchronized playback controls
  across all camera streams.
- Frame-accurate scrubber and keyboard navigation.
- Drag-to-edit timeline segments.
- Episode-level metadata editor.
- Batch selection, batch export, and batch VLM job controls.
- Rerun recordings with camera streams and richer robot state
  visualization.
- Loading/error states for every mutation.
