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

Implemented panels:

- Top navigation shell.
- Dataset browser with dataset open control and summary metrics.
- Episode list with selection.
- Search/filter bar with semantic text search and typed structured filter rows.
- Episode viewer with active camera selection, one `<video>` playback pane,
  loading and error states.
- Timeline panel showing segment annotations.
- Rerun panel that can request a backend session, link the generated `.rrd`,
  and embed ready recordings through the Rerun React viewer.
- Annotation editor with create/update/delete/review actions and midpoint split.
- Export strip for selected episode export.

Current behavior:

- The UI loads API datasets first and falls back to sample data when the API is
  unavailable.
- UI state and API orchestration live in `apps/web/lib/use-studio-data.ts`.
- API adapters live in `apps/web/lib/api.ts`.

Missing UX:

- Simultaneous multi-camera layout and synchronized playback controls across all
  camera streams.
- Frame-accurate scrubber and keyboard navigation.
- Drag-to-edit timeline segments.
- Episode-level metadata editor.
- Batch selection, batch export, and batch VLM job controls.
- Rerun recordings with camera streams and richer robot state visualization.
- Loading/error states for every mutation.
