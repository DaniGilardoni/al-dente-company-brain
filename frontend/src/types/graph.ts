export type NodeGroup =
  | "customer"
  | "product"
  | "material"
  | "supplier"
  | "document";

export interface GraphNode {
  id: string;
  label: string;
  group: NodeGroup;
  title?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface EntityNodeData extends Record<string, unknown> {
  label: string;
  nodeId: string;
  group: NodeGroup;
  title: string;
  highlighted: boolean;
  dimmed: boolean;
  hovered: boolean;
  connectionCount: number;
}
