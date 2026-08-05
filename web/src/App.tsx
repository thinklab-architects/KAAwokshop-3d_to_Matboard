import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "./api";
import { area, num } from "./format";
import Guide from "./Guide";
import { loadModel, type LoadedModel } from "./model";
import { ProjectList, RegionPanel, TakeoffPanel, Uploader } from "./panels";
import type { Project } from "./types";
import Viewer from "./Viewer";

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [current, setCurrent] = useState<Project | null>(null);
  const [model, setModel] = useState<LoadedModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [isolate, setIsolate] = useState<number | null>(null);
  const [sectionZ, setSectionZ] = useState<number | null>(null);
  const [tab, setTab] = useState<"region" | "takeoff">("region");
  const [fitToken, setFitToken] = useState(0);
  const [sdkInfo, setSdkInfo] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  const [net, setNet] = useState(false);

  const modelRef = useRef<LoadedModel | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    api.health().then((h) => setSdkInfo(h.sketchup)).catch(() => setSdkInfo(null));
  }, [refresh]);

  // Load the selected project's geometry.
  useEffect(() => {
    if (!current) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSelected(null);
    setHovered(null);
    setIsolate(null);
    setSectionZ(null);

    loadModel(api.projectBase(current.id), controller.signal)
      .then((m) => {
        modelRef.current?.dispose();
        modelRef.current = m;
        setModel(m);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [current]);

  useEffect(() => () => modelRef.current?.dispose(), []);

  // Which materials to leave out of the totals is a judgement about the model,
  // so it is remembered per project rather than reset on every visit.
  const excludeKey = current ? `matboard.excluded.${current.id}` : null;
  useEffect(() => {
    if (!excludeKey) return;
    try {
      const raw = JSON.parse(localStorage.getItem(excludeKey) ?? "null");
      const ids = Array.isArray(raw) ? raw : (raw?.excluded ?? []);
      setExcluded(new Set<number>(ids));
      setNet(Boolean(raw?.net));
    } catch {
      setExcluded(new Set());
      setNet(false);
    }
  }, [excludeKey]);

  const persist = useCallback(
    (ids: Set<number>, deductOverlaps: boolean) => {
      if (!excludeKey) return;
      try {
        localStorage.setItem(
          excludeKey,
          JSON.stringify({ excluded: [...ids], net: deductOverlaps }),
        );
      } catch {
        /* private mode - the choice just will not persist */
      }
    },
    [excludeKey],
  );

  const changeExcluded = useCallback(
    (next: Set<number>) => {
      setExcluded(next);
      persist(next, net);
    },
    [persist, net],
  );

  const changeNet = useCallback(
    (next: boolean) => {
      setNet(next);
      persist(excluded, next);
    },
    [persist, excluded],
  );

  // Shift+Z is Zoom Extents in SketchUp.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
      if (e.shiftKey && e.key.toLowerCase() === "z") {
        e.preventDefault();
        setFitToken((t) => t + 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const doc = model?.doc ?? null;
  const activeRegion =
    doc && selected !== null ? doc.regions[selected] ?? null : null;
  const hoverRegion = doc && hovered !== null ? doc.regions[hovered] ?? null : null;

  const onUploaded = async (project: Project) => {
    await refresh();
    setCurrent(project);
  };

  const onDelete = async (project: Project) => {
    if (!confirm(`刪除專案「${project.name}」？`)) return;
    await api.deleteProject(project.id);
    if (current?.id === project.id) {
      setCurrent(null);
      setModel(null);
      modelRef.current?.dispose();
      modelRef.current = null;
    }
    refresh();
  };

  const pickRegion = useCallback((id: number) => {
    setSelected(id);
    setTab("region");
  }, []);

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo" />
          <div>
            <h1>建材彙整</h1>
            <span className="sub">SketchUp 模型材質與尺寸擷取</span>
          </div>
        </div>
        <div className="header-right">
          {doc && (
            <div className="model-stats">
            <span>
              <b>{doc.stats.regions}</b> 區塊
            </span>
            <span>
              <b>{doc.materials.length}</b> 材質
            </span>
            <span>
              <b>{num(doc.bbox.size[0], 1)} × {num(doc.bbox.size[1], 1)} × {num(doc.bbox.size[2], 1)}</b> m
            </span>
              <span>
                {excluded.size > 0 || net ? "計入面積" : "總面積"}{" "}
                <b>
                  {area(
                    doc.regions
                      .filter((r) => !excluded.has(r.materialId))
                      .reduce((s, r) => s + (net ? r.exposedAreaM2 : r.areaM2), 0),
                  )}
                </b>
              </span>
              <button onClick={() => setFitToken((t) => t + 1)}>重置視角</button>
            </div>
          )}
          <button className="guide-btn" onClick={() => setGuideOpen(true)}>
            使用說明
          </button>
        </div>
      </header>

      <aside className="left">
        <Uploader onUploaded={onUploaded} upload={api.uploadProject} />
        <h3>專案</h3>
        <ProjectList
          projects={projects}
          currentId={current?.id ?? null}
          onOpen={setCurrent}
          onDelete={onDelete}
        />
        {sdkInfo && <p className="hint sdk">解析引擎：{sdkInfo}</p>}
      </aside>

      <main>
        <Viewer
          model={model}
          selected={selected}
          onSelect={setSelected}
          onHover={setHovered}
          isolateMaterial={isolate}
          sectionZ={sectionZ}
          fitToken={fitToken}
        />
        {doc && (
          <div className="section-tool">
            <label>
              <input
                type="checkbox"
                checked={sectionZ !== null}
                onChange={(e) =>
                  setSectionZ(
                    e.target.checked
                      ? doc.bbox.min[2] + (doc.bbox.max[2] - doc.bbox.min[2]) * 0.6
                      : null,
                  )
                }
              />
              水平剖面
            </label>
            {sectionZ !== null && (
              <>
                <input
                  type="range"
                  min={doc.bbox.min[2]}
                  max={doc.bbox.max[2]}
                  step={0.01}
                  value={sectionZ}
                  onChange={(e) => setSectionZ(Number(e.target.value))}
                />
                <span className="section-z">
                  剖面高 {sectionZ >= 0 ? "+" : ""}
                  {num(sectionZ, 2)} m
                </span>
              </>
            )}
          </div>
        )}
        {loading && <div className="overlay">讀取模型中…</div>}
        {!current && !loading && (
          <div className="overlay">
            <div className="welcome">
              <h2>上傳 SketchUp 模型</h2>
              <p>
                伺服器會直接解析 .skp，取出每個面的材質、位置與尺寸。
                <br />
                不需要在這台電腦上開啟 SketchUp。
              </p>
              <button className="primary welcome-guide" onClick={() => setGuideOpen(true)}>
                看使用說明
              </button>
            </div>
          </div>
        )}
        {error && <div className="overlay err-overlay">{error}</div>}
        {doc && (
          <ul className="controls-hint">
            <li>
              <kbd>中鍵</kbd> 拖曳旋轉
            </li>
            <li>
              <kbd>Shift + 中鍵</kbd> 拖曳平移
            </li>
            <li>
              <kbd>滾輪</kbd> 往游標縮放
            </li>
            <li>
              <kbd>Shift + Z</kbd> 顯示全部
            </li>
            <li>
              <kbd>點擊</kbd> 選取面
            </li>
          </ul>
        )}
        {hoverRegion && doc && (
          <div className="hover-chip">
            <span className="chip-mat">{doc.materials[hoverRegion.materialId].name}</span>
            <span>
              {num(hoverRegion.lengthM, 2)} × {num(hoverRegion.widthM, 2)} m ·{" "}
              {area(hoverRegion.areaM2)}
            </span>
          </div>
        )}
      </main>

      <aside className="right">
        {doc && current ? (
          <>
            <nav className="tabs">
              <button
                className={tab === "region" ? "active" : ""}
                onClick={() => setTab("region")}
              >
                選取面
              </button>
              <button
                className={tab === "takeoff" ? "active" : ""}
                onClick={() => setTab("takeoff")}
              >
                建材彙整
              </button>
            </nav>
            {tab === "region" ? (
              <RegionPanel doc={doc} projectId={current.id} region={activeRegion} />
            ) : (
              <TakeoffPanel
                doc={doc}
                projectId={current.id}
                projectName={current.name}
                isolate={isolate}
                onIsolate={setIsolate}
                onPickRegion={pickRegion}
                excluded={excluded}
                onExcludedChange={changeExcluded}
                net={net}
                onNetChange={changeNet}
              />
            )}
          </>
        ) : (
          <div className="empty">
            <p>尚未載入模型</p>
          </div>
        )}
      </aside>

      {guideOpen && <Guide onClose={() => setGuideOpen(false)} />}
    </div>
  );
}
