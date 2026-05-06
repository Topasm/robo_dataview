export type SignalPresetSource = "placeholder" | "robot_config" | "dataset_schema";

export type SignalPreset = {
  id: string;
  label: string;
  source: SignalPresetSource;
  stateChannels: number[];
  actionChannels: number[];
  description?: string;
};

/**
 * Placeholder signal presets until we have the robot_config mapping.
 * Uses neutral index names instead of body parts (e.g. "State 0–5").
 */
export const HUMANOID_SIGNAL_PRESETS: SignalPreset[] = [
  {
    id: "overview",
    label: "Overview",
    source: "placeholder",
    stateChannels: [],
    actionChannels: [],
    description: "State/action norm only"
  },
  {
    id: "state_0_5",
    label: "State 0–5",
    source: "placeholder",
    stateChannels: [0, 1, 2, 3, 4, 5],
    actionChannels: []
  },
  {
    id: "state_6_11",
    label: "State 6–11",
    source: "placeholder",
    stateChannels: [6, 7, 8, 9, 10, 11],
    actionChannels: []
  },
  {
    id: "action_0_5",
    label: "Action 0–5",
    source: "placeholder",
    stateChannels: [],
    actionChannels: [0, 1, 2, 3, 4, 5]
  },
  {
    id: "action_6_11",
    label: "Action 6–11",
    source: "placeholder",
    stateChannels: [],
    actionChannels: [6, 7, 8, 9, 10, 11]
  }
];
