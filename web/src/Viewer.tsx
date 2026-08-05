import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { regionIndexSubset, type LoadedModel } from "./model";

interface Props {
  model: LoadedModel | null;
  selected: number | null;
  onSelect: (regionId: number | null) => void;
  onHover: (regionId: number | null) => void;
  /** When set, everything on other materials fades back. */
  isolateMaterial: number | null;
  /** Horizontal section height in metres; everything above it is cut away. */
  sectionZ: number | null;
  fitToken: number;
}

/** Parked far above any real building, so nothing is clipped when off. */
const NO_SECTION = 1e9;

// Deliberately not the UI's clay accent: the models themselves are sand, timber
// and concrete, so an earth-toned highlight would vanish into whatever it lands
// on. Blue is the one hue no building material claims - and it is what SketchUp
// highlights a selection with, so it reads correctly straight away.
const SELECT_COLOR = 0x1f6fd0;
const HOVER_COLOR = 0xdd8a1c;

// Keep in step with the CSS palette in styles.css.
const SCENE_BG = 0xe3dbcb;
const GRID_MAJOR = 0xc0b298;
const GRID_MINOR = 0xd5cab4;

/** A sky-to-ground gradient for smooth surfaces to reflect.
 *
 * Without one, water and glass have nothing to catch: they shade to a single
 * flat tone and read as black paint rather than as water. Built from geometry
 * rather than an image so the page stays self-contained, and via `fromScene`
 * rather than an equirectangular texture so it inherits the scene's Z-up world
 * instead of needing the environment rotated into it.
 */
function buildEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture {
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();

  const R = 50;
  const shell = new THREE.SphereGeometry(R, 24, 16);
  const sky = new THREE.Color(0xb9d0ea);
  const horizon = new THREE.Color(0xf6efe3);
  const ground = new THREE.Color(0xb4a790);
  const pos = shell.attributes.position;
  const colours = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const t = pos.getZ(i) / R; // -1 below, +1 overhead
    const c =
      t >= 0
        ? horizon.clone().lerp(sky, Math.min(t * 1.5, 1))
        : horizon.clone().lerp(ground, Math.min(-t * 1.8, 1));
    colours.set([c.r, c.g, c.b], i * 3);
  }
  shell.setAttribute("color", new THREE.BufferAttribute(colours, 3));
  const dome = new THREE.Mesh(
    shell,
    new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide }),
  );
  env.add(dome);

  // A bright patch, so smooth surfaces get a highlight and not just a wash.
  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(7, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0xfff6e6 }),
  );
  sun.position.set(12, -24, 32);
  env.add(sun);

  const target = pmrem.fromScene(env, 0.05);
  shell.dispose();
  (dome.material as THREE.Material).dispose();
  sun.geometry.dispose();
  (sun.material as THREE.Material).dispose();
  pmrem.dispose();
  return target.texture;
}

export default function Viewer({
  model,
  selected,
  onSelect,
  onHover,
  isolateMaterial,
  sectionZ,
  fitToken,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    raycaster: THREE.Raycaster;
    clip: THREE.Plane;
    root: THREE.Group;
    mesh: THREE.Mesh | null;
    selectMesh: THREE.Mesh;
    hoverMesh: THREE.Mesh;
    grid: THREE.GridHelper | null;
    model: LoadedModel | null;
  } | null>(null);

  // --- one-time scene setup -------------------------------------------------
  useEffect(() => {
    const host = hostRef.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.localClippingEnabled = true;
    host.appendChild(renderer.domElement);

    // Keeps everything below the plane. Interior floors sit under an opaque
    // roof, so without a way to cut down through it they cannot be seen - and
    // a raycast can only ever return what is in front.
    const clip = new THREE.Plane(new THREE.Vector3(0, 0, -1), NO_SECTION);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(SCENE_BG);
    const environment = buildEnvironment(renderer);
    scene.environment = environment;

    // SketchUp is Z-up; keep the model in its own coordinates so the numbers in
    // the panel match the model's own origin, and point the camera the right way.
    const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 5000);
    camera.up.set(0, 0, 1);
    camera.position.set(24, -28, 16);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.98;

    // SketchUp's navigation, so the muscle memory carries over: middle-drag
    // orbits, shift+middle-drag pans, the wheel zooms toward the cursor rather
    // than the view centre. OrbitControls turns a ROTATE binding into a pan on
    // its own when shift is held, so the pair falls out of one assignment.
    //
    // Left-drag also orbits, which SketchUp does not do - there the left button
    // belongs to the active tool. It stays because a laptop trackpad has no
    // middle button and would otherwise have no way to orbit at all; a click
    // still selects, since selection needs the pointer to stay within 4px.
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.ROTATE,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.zoomToCursor = true;
    controls.screenSpacePanning = true;

    // Warm daylight bounced off a sand-coloured ground, to sit in the light room
    // rather than the dark one this started as.
    scene.add(new THREE.HemisphereLight(0xfff6e8, 0xbfae93, 2.0));
    const key = new THREE.DirectionalLight(0xfffaf0, 1.75);
    key.position.set(0.6, -1, 1.4);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xe8ddc9, 0.55);
    fill.position.set(-1, 0.7, 0.4);
    scene.add(fill);

    const root = new THREE.Group();
    scene.add(root);

    const overlay = (color: number, opacity: number) => {
      const m = new THREE.Mesh(
        new THREE.BufferGeometry(),
        new THREE.MeshBasicMaterial({
          color,
          transparent: true,
          opacity,
          side: THREE.DoubleSide,
          depthTest: true,
          depthWrite: false,
          polygonOffset: true,
          polygonOffsetFactor: -4,
          polygonOffsetUnits: -4,
          clippingPlanes: [clip],
        }),
      );
      m.visible = false;
      m.renderOrder = 10;
      scene.add(m);
      return m;
    };
    const selectMesh = overlay(SELECT_COLOR, 0.5);
    const hoverMesh = overlay(HOVER_COLOR, 0.38);

    const raycaster = new THREE.Raycaster();
    stateRef.current = {
      renderer, scene, camera, controls, raycaster, clip, root,
      mesh: null, selectMesh, hoverMesh, grid: null, model: null,
    };

    // Size before the first render, or the first frame goes out at the canvas
    // element's 300x150 default.
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = host;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    let running = true;
    const tick = () => {
      if (!running) return;
      controls.update();
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    };
    tick();

    if (import.meta.env.DEV) {
      (window as unknown as Record<string, unknown>).__viewer = stateRef.current;
    }

    return () => {
      running = false;
      ro.disconnect();
      controls.dispose();
      selectMesh.geometry.dispose();
      (selectMesh.material as THREE.Material).dispose();
      hoverMesh.geometry.dispose();
      (hoverMesh.material as THREE.Material).dispose();
      environment.dispose();
      renderer.dispose();
      host.removeChild(renderer.domElement);
      stateRef.current = null;
    };
  }, []);

  // --- swap in a new model --------------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s) return;

    if (s.mesh) {
      s.root.remove(s.mesh);
      s.mesh = null;
    }
    if (s.grid) {
      s.scene.remove(s.grid);
      s.grid.geometry.dispose();
      (s.grid.material as THREE.Material).dispose();
      s.grid = null;
    }
    s.selectMesh.visible = false;
    s.hoverMesh.visible = false;
    s.model = model;
    if (!model) return;

    for (const m of model.materials) m.clippingPlanes = [s.clip];
    const mesh = new THREE.Mesh(model.geometry, model.materials);
    s.root.add(mesh);
    s.mesh = mesh;

    // Overlays share the model's position buffer and only swap their index.
    for (const o of [s.selectMesh, s.hoverMesh]) {
      o.geometry.dispose();
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", model.geometry.getAttribute("position"));
      o.geometry = g;
    }

    const box = model.geometry.boundingBox!;
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const span = Math.max(size.x, size.y, size.z, 1);

    const divisions = Math.max(10, Math.ceil(span / 2));
    const grid = new THREE.GridHelper(divisions * 2, divisions, GRID_MAJOR, GRID_MINOR);
    grid.rotation.x = Math.PI / 2; // GridHelper is XZ by default; we are Z-up.
    grid.position.set(center.x, center.y, box.min.z - 0.02);
    s.scene.add(grid);
    s.grid = grid;

    s.controls.target.copy(center);
    s.camera.position.set(center.x + span * 0.9, center.y - span * 1.15, center.z + span * 0.75);
    s.camera.near = span / 500;
    s.camera.far = span * 60;
    s.camera.updateProjectionMatrix();
    s.controls.update();
  }, [model]);

  // --- re-fit on demand -----------------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s || !s.model || fitToken === 0) return;
    const box = s.model.geometry.boundingBox!;
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const span = Math.max(size.x, size.y, size.z, 1);
    s.controls.target.copy(center);
    s.camera.position.set(center.x + span * 0.9, center.y - span * 1.15, center.z + span * 0.75);
    s.controls.update();
  }, [fitToken]);

  // --- horizontal section ---------------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s) return;
    s.clip.constant = sectionZ === null ? NO_SECTION : sectionZ;
  }, [sectionZ, model]);

  // --- selection + hover overlays ------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s || !s.model) return;
    applyOverlay(s.selectMesh, s.model, selected);
  }, [selected, model]);

  // --- material isolation ---------------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    if (!s || !s.model) return;
    s.model.materials.forEach((m, i) => {
      const std = m as THREE.MeshStandardMaterial;
      const doc = s.model!.doc.materials[i];
      const dimmed = isolateMaterial !== null && isolateMaterial !== i;
      if (dimmed) {
        std.transparent = true;
        std.opacity = 0.06;
        std.depthWrite = false;
      } else {
        const nativelyTransparent = doc.opacity < 0.99;
        std.transparent = nativelyTransparent;
        std.opacity = nativelyTransparent ? doc.opacity : 1;
        std.depthWrite = !nativelyTransparent;
      }
      std.needsUpdate = true;
    });
  }, [isolateMaterial, model]);

  // --- pointer interaction --------------------------------------------------
  useEffect(() => {
    const s = stateRef.current;
    const host = hostRef.current;
    if (!s || !host) return;

    const ndc = new THREE.Vector2();
    let down: { x: number; y: number } | null = null;

    const pick = (ev: PointerEvent): number | null => {
      if (!s.mesh || !s.model) return null;
      const rect = host.getBoundingClientRect();
      ndc.set(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );
      // The render loop normally keeps this current, but it is paused whenever
      // the tab is hidden - and a stale matrix aims the ray somewhere else.
      s.camera.updateMatrixWorld();
      s.raycaster.setFromCamera(ndc, s.camera);
      const hits = s.raycaster.intersectObject(s.mesh, false);
      for (const hit of hits) {
        if (!hit.face) continue;
        // The raycaster ignores clipping planes, so a cut-away roof would still
        // swallow every click aimed at the floor underneath it.
        if (sectionZ !== null && hit.point.z > sectionZ) continue;
        const region = s.model.regionIds[hit.face.a];
        // Ignore surfaces faded out by an isolate filter.
        if (isolateMaterial !== null) {
          const r = s.model.doc.regions[region];
          if (r && r.materialId !== isolateMaterial) continue;
        }
        return region;
      }
      return null;
    };

    const onPointerDown = (ev: PointerEvent) => {
      down = { x: ev.clientX, y: ev.clientY };
    };
    const onPointerUp = (ev: PointerEvent) => {
      if (!down) return;
      const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y);
      down = null;
      if (moved > 4) return; // that was an orbit, not a click
      onSelect(pick(ev));
    };
    const onPointerMove = (ev: PointerEvent) => {
      if (down) return;
      const region = pick(ev);
      host.style.cursor = region === null ? "default" : "pointer";
      if (s.model) applyOverlay(s.hoverMesh, s.model, region);
      onHover(region);
    };
    const onPointerLeave = () => {
      if (s.model) applyOverlay(s.hoverMesh, s.model, null);
      onHover(null);
    };

    host.addEventListener("pointerdown", onPointerDown);
    host.addEventListener("pointerup", onPointerUp);
    host.addEventListener("pointermove", onPointerMove);
    host.addEventListener("pointerleave", onPointerLeave);
    return () => {
      host.removeEventListener("pointerdown", onPointerDown);
      host.removeEventListener("pointerup", onPointerUp);
      host.removeEventListener("pointermove", onPointerMove);
      host.removeEventListener("pointerleave", onPointerLeave);
    };
  }, [model, onSelect, onHover, isolateMaterial, sectionZ]);

  return <div className="viewer" ref={hostRef} />;
}

function applyOverlay(mesh: THREE.Mesh, model: LoadedModel, regionId: number | null) {
  if (regionId === null || regionId === undefined) {
    mesh.visible = false;
    return;
  }
  const subset = regionIndexSubset(model, regionId);
  if (!subset.length) {
    mesh.visible = false;
    return;
  }
  mesh.geometry.setIndex(new THREE.BufferAttribute(subset, 1));
  mesh.geometry.setDrawRange(0, subset.length);
  mesh.visible = true;
}
