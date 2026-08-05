import * as THREE from "three";
import type { ModelDoc } from "./types";

export interface LoadedModel {
  doc: ModelDoc;
  geometry: THREE.BufferGeometry;
  materials: THREE.Material[];
  /** Region id per vertex - this is what turns a raycast hit into a surface. */
  regionIds: Uint32Array;
  index: Uint32Array;
  /** Region id -> the triangles belonging to it, for building highlight overlays. */
  regionTriangles: Map<number, Uint32Array>;
  dispose(): void;
}

function view(
  buffer: ArrayBuffer,
  info: { byteOffset: number; byteLength: number; componentType: string; components: number },
) {
  const count = info.byteLength / (info.componentType === "f32" ? 4 : 4);
  return info.componentType === "f32"
    ? new Float32Array(buffer, info.byteOffset, count)
    : new Uint32Array(buffer, info.byteOffset, count);
}

function buildRegionTriangles(index: Uint32Array, regionIds: Uint32Array) {
  const triCount = index.length / 3;
  const counts = new Map<number, number>();
  for (let t = 0; t < triCount; t++) {
    const r = regionIds[index[t * 3]];
    counts.set(r, (counts.get(r) ?? 0) + 1);
  }
  const out = new Map<number, Uint32Array>();
  const cursor = new Map<number, number>();
  for (const [r, c] of counts) {
    out.set(r, new Uint32Array(c));
    cursor.set(r, 0);
  }
  for (let t = 0; t < triCount; t++) {
    const r = regionIds[index[t * 3]];
    const arr = out.get(r)!;
    arr[cursor.get(r)!] = t;
    cursor.set(r, cursor.get(r)! + 1);
  }
  return out;
}

export function regionIndexSubset(model: LoadedModel, regionId: number): Uint32Array {
  const tris = model.regionTriangles.get(regionId);
  if (!tris) return new Uint32Array(0);
  const out = new Uint32Array(tris.length * 3);
  for (let i = 0; i < tris.length; i++) {
    const t = tris[i] * 3;
    out[i * 3] = model.index[t];
    out[i * 3 + 1] = model.index[t + 1];
    out[i * 3 + 2] = model.index[t + 2];
  }
  return out;
}

export async function loadModel(base: string, signal?: AbortSignal): Promise<LoadedModel> {
  // Both live at a fixed URL but are rewritten whenever the project is
  // reconverted, so always revalidate: a stale copy silently shows the previous
  // conversion's numbers. "no-cache" still returns a cheap 304 when unchanged.
  const opts: RequestInit = { signal, cache: "no-cache" };
  const [doc, bin] = await Promise.all([
    fetch(`${base}/model.json`, opts).then((r) => {
      if (!r.ok) throw new Error(`model.json: ${r.status}`);
      return r.json() as Promise<ModelDoc>;
    }),
    fetch(`${base}/mesh.bin`, opts).then((r) => {
      if (!r.ok) throw new Error(`mesh.bin: ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);

  const attrs = doc.mesh.attributes;
  const position = view(bin, attrs.position) as Float32Array;
  const normal = view(bin, attrs.normal) as Float32Array;
  const uv = view(bin, attrs.uv) as Float32Array;
  const regionIds = view(bin, attrs.regionId) as Uint32Array;
  const index = new Uint32Array(bin, doc.mesh.index.byteOffset, doc.mesh.index.count);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normal, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  for (const g of doc.mesh.groups) {
    geometry.addGroup(g.indexStart, g.indexCount, g.materialId);
  }
  geometry.computeBoundingSphere();
  geometry.computeBoundingBox();

  const loader = new THREE.TextureLoader();
  const materials = await Promise.all(
    doc.materials.map(async (m) => {
      // Anything the model made see-through is water or glazing, and both want
      // a near-mirror finish: matte shading gives them nothing to reflect and
      // they end up reading as flat dark paint.
      const smooth = m.opacity < 0.99;
      const mat = new THREE.MeshStandardMaterial({
        // Colour management is on by default since three r152, so the hex is
        // already read as sRGB and stored linear. Converting again here turned
        // every untextured material nearly black - the textured ones escaped it
        // only because their colour is overwritten with white below.
        color: new THREE.Color(m.colorHex),
        roughness: smooth ? 0.06 : 0.85,
        metalness: smooth ? 0.0 : 0.02,
        // Enough for surfaces to pick up the sky without washing out the
        // material colours the takeoff is about.
        envMapIntensity: smooth ? 1.4 : 0.3,
        side: THREE.DoubleSide,
        name: m.name,
      });
      if (smooth) {
        mat.transparent = true;
        mat.opacity = m.opacity;
        mat.depthWrite = false;
      }
      if (m.texture) {
        try {
          const tex = await loader.loadAsync(`${base}/${m.texture}`);
          tex.wrapS = THREE.RepeatWrapping;
          tex.wrapT = THREE.RepeatWrapping;
          tex.colorSpace = THREE.SRGBColorSpace;
          tex.anisotropy = 8;
          mat.map = tex;
          // The texture already carries the colour; tinting again darkens it.
          mat.color.set(0xffffff);
          mat.needsUpdate = true;
        } catch {
          /* keep the flat colour if the image is missing */
        }
      }
      return mat as THREE.Material;
    }),
  );

  return {
    doc,
    geometry,
    materials,
    regionIds,
    index,
    regionTriangles: buildRegionTriangles(index, regionIds),
    dispose() {
      geometry.dispose();
      for (const m of materials) {
        const std = m as THREE.MeshStandardMaterial;
        std.map?.dispose();
        m.dispose();
      }
    },
  };
}
