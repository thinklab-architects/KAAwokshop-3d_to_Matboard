/** Mirrors the `matboard/1.0` document written by the Python converter. */

export interface Material {
  id: number;
  name: string;
  colorHex: string;
  opacity: number;
  texture: string | null;
  textureSizeM: [number, number] | null;
  attrs: Record<string, Record<string, unknown>> | null;
}

export interface Element {
  id: number;
  name: string;
  kind: "group" | "instance" | "model";
  path: string;
  parent: number | null;
  tag: string | null;
  attrs: Record<string, Record<string, unknown>> | null;
}

export interface Region {
  id: number;
  materialId: number;
  category: string;
  categoryLabel: string;
  elementId: number;
  tag: string | null;
  areaM2: number;
  /** Part of this surface buried under a coplanar counterpart. */
  hiddenM2: number;
  /** areaM2 - hiddenM2: what is actually there to be finished. */
  exposedAreaM2: number;
  overlapWith: {
    regionId: number;
    m2: number;
    /** interface = two solids meeting, duplicate = drawn twice, plate = the
     *  other skin of one thin element. */
    kind: "interface" | "duplicate" | "plate";
  }[];
  /** Set when this face is one batten of a screen counted as a whole panel. */
  assemblyId: number | null;
  /** Outline shape the dimensions were read from. */
  shape: "rectangle" | "triangle" | "polygon" | "unknown";
  /** Every edge length of the real outline, collinear points already merged. */
  edgesM: number[];
  lengthM: number;
  widthM: number;
  /** What the pair means, e.g. "寬 × 高", "底 × 高", or "長 × 寬（範圍）". */
  dimLabel: string;
  /** area / outline area; below 1 means the face has openings cut out of it. */
  solidRatio: number;
  normal: [number, number, number];
  centroid: [number, number, number];
  bbox: { min: [number, number, number]; max: [number, number, number] };
  faceCount: number;
  triangleCount: number;
}

export interface MeshGroup {
  materialId: number;
  indexStart: number;
  indexCount: number;
  transparent: boolean;
}

export interface ModelDoc {
  schema: string;
  source: {
    file: string;
    modelName: string | null;
    skpVersion: string;
    generatedAt: string;
    converter: string;
  };
  units: { length: string; area: string };
  upAxis: "Z";
  bbox: { min: number[]; max: number[]; size: number[] };
  stats: {
    faces: number;
    regions: number;
    triangles: number;
    vertices: number;
    elements: number;
    skippedHidden: number;
  };
  totals: { areaM2: number; hiddenM2: number; exposedAreaM2: number };
  overlaps: {
    pairCount: number;
    duplicatePairs: number;
    interfacePairs: number;
    platePairs: number;
    hiddenM2: number;
  };
  /** Runs of battens counted as one panel instead of stick by stick. */
  assemblies: {
    id: number;
    name: string;
    kind: string;
    materialId: number;
    members: number;
    category: string;
    categoryLabel: string;
    regionIds: number[];
    areaM2: number;
    /** What a face-by-face sum would have given, so the change is auditable. */
    rawAreaM2: number;
    widthM: number;
    heightM: number;
    bbox: { min: number[]; max: number[] };
  }[];
  materials: Material[];
  elements: Element[];
  regions: Region[];
  summary: {
    byMaterial: {
      materialId: number;
      name: string;
      areaM2: number;
      exposedAreaM2: number;
      regionCount: number;
      categories: Record<string, number>;
    }[];
    byCategory: {
      category: string;
      label: string;
      areaM2: number;
      exposedAreaM2: number;
      regionCount: number;
    }[];
  };
  mesh: {
    file: string;
    vertexCount: number;
    attributes: Record<
      string,
      { byteOffset: number; byteLength: number; componentType: string; components: number }
    >;
    index: { byteOffset: number; byteLength: number; componentType: string; count: number };
    groups: MeshGroup[];
  };
}

export interface Project {
  id: string;
  name: string;
  originalName: string;
  sizeBytes: number;
  uploadedAt: string;
  status: "converting" | "ready" | "error";
  error?: string;
  skpVersion?: string;
  materialCount?: number;
  stats?: ModelDoc["stats"];
  bbox?: ModelDoc["bbox"];
}
