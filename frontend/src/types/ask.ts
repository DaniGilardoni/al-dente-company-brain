export type Verticale = "crm" | "erp" | "calls" | "kb";

export interface AskResponse {
  answer: string;
  sources: string[];
  verticale: Verticale;
  artifact_url?: string | null;
}

export interface Turn {
  id: number;
  question: string;
  answer: AskResponse | null;
  error: string | null;
}

/** An archived chat (a full thread of turns). */
export interface HistoryItem {
  id: number;
  question: string; // first question — used as the title
  turns: Turn[];
  at: number;
}

export interface UiHints {
  active_tools?: string[];
  highlight_nodes?: string[];
  reasoning_path?: string[][];
}

export type ToolId = "crm" | "erp" | "kb" | "calls";
export type ToolStatus = "idle" | "active" | "used";

export interface ToolState {
  id: ToolId;
  status: ToolStatus;
  evidenceCount: number;
}
