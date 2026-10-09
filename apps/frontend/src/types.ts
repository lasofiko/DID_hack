export type Point = {x: number; y: number};
export type Session = {scenario: string; seed: number; mode: string; planner_mode: string};
export type Entry = {sim_time: number; stage: string; text: string; hypothesis_id: string};
export type Cost = {cell: Point; energy_per_m: number; uncertainty: number|null; energy_per_rad: number|null; turn_uncertainty: number|null; move_samples: number; turn_samples: number};
export type Telemetry = {connection: string; session: Session; state: {status: string; collected: number; delivered: number; goal: {action: string; target: Point|null; reason: string}|null; observation: {battery: number; signal: number; sim_time: number}|null}; robot_pose: Point|null; robot_yaw: number; trajectory: Point[]; planned_path: Point[]; knowledge: Cost[]; energy_diagnostics: {accepted: number; rejected: Record<string, number>; model: string; adaptive: boolean}|null; journal: Entry[]; planner_source: string; collected_positions: Point[]; events: {type: string; sim_time: number}[]; map_revision: number; error: string|null};
export type Grid = {width: number; height: number; resolution: number; origin: Point; origin_yaw: number; data: number[]; revision: number};
