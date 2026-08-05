import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { projectBase } from "./api";
import { area, bytes, downloadCsv, length, num, when } from "./format";
import type { ModelDoc, Project, Region } from "./types";

// ---------------------------------------------------------------------------
// selected surface
// ---------------------------------------------------------------------------

const empty = (v: unknown) => v === null || v === undefined || v === "";

const SHAPE_LABEL: Record<string, string> = {
  rectangle: "矩形",
  triangle: "三角形",
  polygon: "多邊形",
  unknown: "未判定",
};

function AttrTable({ attrs }: { attrs: Record<string, Record<string, unknown>> | null }) {
  if (!attrs) return null;
  // Blank entries are noise; the model author left them unfilled.
  const dicts = Object.entries(attrs)
    .map(([d, e]) => [d, Object.entries(e).filter(([, v]) => !empty(v))] as const)
    .filter(([, e]) => e.length);
  if (!dicts.length) return null;
  return (
    <>
      {dicts.map(([dict, entries]) => (
        <div key={dict} className="attr-block">
          <div className="attr-dict">{dict}</div>
          <dl className="kv">
            {entries.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </>
  );
}

function countAttrs(attrs: Record<string, Record<string, unknown>> | null): number {
  if (!attrs) return 0;
  return Object.values(attrs).reduce(
    (n, e) => n + Object.values(e).filter((v) => !empty(v)).length,
    0,
  );
}

function Fold({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <section className="fold">
      <button className="fold-head" onClick={() => setOpen(!open)}>
        <span className="caret">{open ? "▾" : "▸"}</span>
        {title}
        {count !== undefined && <span className="fold-count">{count}</span>}
      </button>
      {open && <div className="fold-body">{children}</div>}
    </section>
  );
}

const COMPASS = ["北", "東北", "東", "東南", "南", "西南", "西", "西北"];

/** SketchUp's world is +Y north, +X east, so a normal maps straight to a bearing. */
function orientation(n: [number, number, number]): string {
  const [nx, ny, nz] = n;
  if (nz >= 0.99) return "朝上（水平）";
  if (nz <= -0.99) return "朝下（水平）";
  const bearing = (Math.atan2(nx, ny) * 180) / Math.PI;
  const face = COMPASS[Math.round(((((bearing % 360) + 360) % 360) / 45)) % 8];
  // Angle of the surface away from horizontal: 0 for a slab, 90 for a wall.
  const tilt = Math.round((Math.acos(Math.min(1, Math.abs(nz))) * 180) / Math.PI);
  if (tilt >= 82) return `朝${face}`;
  return `朝${face} · 傾斜 ${tilt}°`;
}

const level = (z: number) => `${z >= 0 ? "+" : ""}${num(z, 2)}`;

export function RegionPanel({
  doc,
  projectId,
  region,
}: {
  doc: ModelDoc;
  projectId: string;
  region: Region | null;
}) {
  if (!region) {
    return (
      <div className="empty">
        <p>在模型上點選任一面</p>
        <span>牆面、地板、屋頂 —— 會顯示該區塊的材質與尺寸</span>
      </div>
    );
  }

  const material = doc.materials[region.materialId];
  const element = doc.elements[region.elementId];
  // Only worth showing when the element is actually nested inside something.
  const nested = element.path.split("/").filter(Boolean).length > 1;
  const [zLo, zHi] = [region.bbox.min[2], region.bbox.max[2]];
  const attrCount = countAttrs(element.attrs) + countAttrs(material.attrs);

  return (
    <div className="region-panel">
      <div className="mat-head">
        <span
          className="swatch lg"
          style={{
            background: material.texture
              ? `url(${projectBase(projectId)}/${material.texture}) center/cover`
              : material.colorHex,
          }}
        />
        <div>
          <h2>{material.name}</h2>
          <div className="chips">
                <span className="chip">{region.categoryLabel}</span>
            <span className="chip ghost">{SHAPE_LABEL[region.shape] ?? region.shape}</span>
            {region.tag && <span className="chip ghost">Tag · {region.tag}</span>}
            {material.opacity < 0.99 && (
              <span className="chip ghost">透明度 {num(material.opacity * 100, 0)}%</span>
            )}
          </div>
        </div>
      </div>

      <div className="metrics">
        <div className="metric big">
          <span className="label">面積</span>
          <span className="value">{area(region.areaM2)}</span>
        </div>
        {region.shape === "triangle" ? (
          region.edgesM.map((e, i) => (
            <div className="metric" key={i}>
              <span className="label">邊 {"abc"[i] ?? i + 1}</span>
              <span className="value">{length(e)}</span>
            </div>
          ))
        ) : (
          <>
            <div className="metric">
              <span className="label">{region.dimLabel.split("×")[0].trim()}</span>
              <span className="value">{length(region.lengthM)}</span>
            </div>
            <div className="metric">
              <span className="label">
                {region.dimLabel.split("×")[1]?.trim() ?? "寬"}
              </span>
              <span className="value">{length(region.widthM)}</span>
            </div>
          </>
        )}
      </div>

      {region.shape === "triangle" && (
        <p className="note subtle">
          三角形面積由三邊實算（{num(region.lengthM, 3)} m 為最長邊，
          對應高 {num(region.widthM, 3)} m）。
        </p>
      )}

      {region.shape === "polygon" && (
        <section>
          <h3>輪廓邊長 · {region.edgesM.length} 段</h3>
          <ul className="edge-list">
            {region.edgesM.map((e, i) => (
              <li key={i}>
                <span>{i + 1}</span>
                {length(e)}
              </li>
            ))}
          </ul>
          <p className="note subtle">
            此面不是矩形，上方「{region.dimLabel}」僅為整體範圍，非邊長。
            面積為實際表面積。
          </p>
        </section>
      )}

      {region.solidRatio < 0.995 && (
        <p className="note">
          此面有開口，面積已扣除：實際表面積為完整輪廓的{" "}
          {num(region.solidRatio * 100, 0)}%。
        </p>
      )}

      {region.assemblyId !== null &&
        (() => {
          const a = doc.assemblies?.find((x) => x.id === region.assemblyId);
          if (!a) return null;
          return (
            <p className="note">
              這一面屬於格柵「{a.name}」（{a.members} 支）。彙整表以整片計算：
              {num(a.widthM, 2)} × {num(a.heightM, 2)} m ＝ <b>{area(a.areaM2)}</b>，
              而非逐面加總的 {area(a.rawAreaM2)}。
            </p>
          );
        })()}

      {region.hiddenM2 > 0.005 && (
        <section>
          <h3>被其他量體覆蓋</h3>
          <div className="metrics">
            <div className="metric">
              <span className="label">埋沒</span>
              <span className="value">{area(region.hiddenM2)}</span>
            </div>
            <div className="metric">
              <span className="label">實際外露</span>
              <span className="value">{area(region.exposedAreaM2)}</span>
            </div>
          </div>
          <ul className="overlap-list">
            {region.overlapWith.map((o) => {
              const other = doc.regions[o.regionId];
              return (
                <li key={o.regionId}>
                  <span className={`tagdot ${o.kind}`} />
                  <span className="ov-name">
                    {doc.elements[other?.elementId]?.name ?? `區塊 ${o.regionId}`}
                    <em>{doc.materials[other?.materialId]?.name}</em>
                  </span>
                  <span className="ov-area">{area(o.m2)}</span>
                </li>
              );
            })}
          </ul>
          <p className="note subtle">
            {region.overlapWith.some((o) => o.kind === "plate")
              ? "這是薄板的另一面（例如樓板底面或玻璃背面）。面材只鋪一次，彙整表只計一面。"
              : region.overlapWith.some((o) => o.kind === "interface")
                ? "與其他量體面對面貼合的部分，兩側都看不到，彙整表可選擇扣除。"
                : "與另一個面完全重合（幾何被畫了兩次），彙整表只計一次。"}
          </p>
        </section>
      )}

      <section>
        <dl className="kv">
          <div>
            <dt>元件</dt>
            <dd>{element.name}</dd>
          </div>
          {nested && (
            <div>
              <dt>位於</dt>
              <dd className="mono">{element.path.replace(/^\//, "")}</dd>
            </div>
          )}
          <div>
            <dt>朝向</dt>
            <dd>{orientation(region.normal)}</dd>
          </div>
          <div>
            <dt>高程</dt>
            <dd className="mono">
              {Math.abs(zHi - zLo) < 0.001
                ? `${level(zLo)} m`
                : `${level(zLo)} ~ ${level(zHi)} m`}
            </dd>
          </div>
          {material.textureSizeM && (
            <div>
              <dt>貼圖單元</dt>
              <dd className="mono">
                {num(material.textureSizeM[0] * 1000, 0)} ×{" "}
                {num(material.textureSizeM[1] * 1000, 0)} mm ·約{" "}
                {num(
                  region.areaM2 / (material.textureSizeM[0] * material.textureSizeM[1]),
                  0,
                )}{" "}
                單元
              </dd>
            </div>
          )}
        </dl>
      </section>

      {attrCount > 0 && (
        <Fold title="模型自帶屬性" count={attrCount}>
          <AttrTable attrs={element.attrs} />
          <AttrTable attrs={material.attrs} />
        </Fold>
      )}

      <Fold title="幾何細節">
        <dl className="kv">
          <div>
            <dt>組成</dt>
            <dd>
              {region.faceCount} 個面 · {region.triangleCount} 三角形
            </dd>
          </div>
          <div>
            <dt>中心點</dt>
            <dd className="mono">
              X {num(region.centroid[0], 3)} Y {num(region.centroid[1], 3)} Z{" "}
              {num(region.centroid[2], 3)}
            </dd>
          </div>
          <div>
            <dt>法線</dt>
            <dd className="mono">{region.normal.map((v) => num(v, 2)).join(", ")}</dd>
          </div>
        </dl>
      </Fold>
    </div>
  );
}

// ---------------------------------------------------------------------------
// takeoff
// ---------------------------------------------------------------------------

/** The Category the model itself records for a material, if it records one. */
export function materialCategory(m: { attrs: ModelDoc["materials"][number]["attrs"] }) {
  for (const dict of Object.values(m.attrs ?? {})) {
    const v = (dict as Record<string, unknown>)?.Category;
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return null;
}

function ReportDialog({
  value,
  basis,
  excludedCount,
  onChange,
  onCancel,
  onConfirm,
}: {
  value: { projectName: string; site: string };
  basis: string;
  excludedCount: number;
  onChange: (next: { projectName: string; site: string }) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const first = useRef<HTMLInputElement>(null);

  // Mount only. Keyed on anything that changes per render - onCancel is a fresh
  // arrow function each time - this re-selects the text after every keystroke,
  // so the next character replaces what was typed and the field never holds
  // more than one.
  useEffect(() => {
    first.current?.focus();
    first.current?.select();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="g-backdrop" onClick={onCancel}>
      <form
        className="g-modal dlg"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm();
        }}
      >
        <header className="g-head">
          <h2>產生 PDF 報表</h2>
          <button type="button" className="g-close" onClick={onCancel} aria-label="關閉">
            ×
          </button>
        </header>

        <div className="g-body">
          <label className="field">
            <span>專案名稱</span>
            <input
              ref={first}
              value={value.projectName}
              onChange={(e) => onChange({ ...value, projectName: e.target.value })}
              placeholder="例如：新竹湖濱住宅"
            />
          </label>
          <label className="field">
            <span>基地</span>
            <input
              value={value.site}
              onChange={(e) => onChange({ ...value, site: e.target.value })}
              placeholder="例如：新竹市東區光復路二段 101 號"
            />
          </label>
          <p className="g-note">
            這兩欄會印在報表抬頭，並記住供下次使用。
            計算基準為<b>{basis}</b>
            {excludedCount > 0 && `，已排除 ${excludedCount} 種材質`}
            ，也會一併印在報表上。
          </p>
        </div>

        <footer className="g-foot">
          <button type="button" onClick={onCancel}>
            取消
          </button>
          <div className="g-dots" />
          <button type="submit" className="primary">
            產生 PDF
          </button>
        </footer>
      </form>
    </div>
  );
}

export function TakeoffPanel({
  doc,
  projectId,
  projectName,
  isolate,
  onIsolate,
  onPickRegion,
  excluded,
  onExcludedChange,
  net,
  onNetChange,
}: {
  doc: ModelDoc;
  projectId: string;
  projectName: string;
  isolate: number | null;
  onIsolate: (id: number | null) => void;
  onPickRegion: (id: number) => void;
  /** Material ids the user has taken out of the totals. */
  excluded: Set<number>;
  onExcludedChange: (next: Set<number>) => void;
  /** Deduct surface buried under coplanar counterparts. */
  net: boolean;
  onNetChange: (next: boolean) => void;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);

  // What the report says on its face. Remembered per project so it does not
  // have to be retyped every time the takeoff is reissued.
  const metaKey = `matboard.report.${projectId}`;
  const [reportMeta, setReportMeta] = useState({ projectName: "", site: "" });
  useEffect(() => {
    let stored: { projectName?: string; site?: string } = {};
    try {
      stored = JSON.parse(localStorage.getItem(metaKey) ?? "{}");
    } catch {
      /* fall through to defaults */
    }
    setReportMeta({
      projectName: stored.projectName ?? projectName,
      site: stored.site ?? "",
    });
  }, [metaKey, projectName]);

  const updateMeta = (next: { projectName: string; site: string }) => {
    setReportMeta(next);
    try {
      localStorage.setItem(metaKey, JSON.stringify(next));
    } catch {
      /* private mode - just will not persist */
    }
  };
  const areaOf = (r: { areaM2: number; exposedAreaM2: number }) =>
    net ? r.exposedAreaM2 : r.areaM2;
  const maxArea = Math.max(...doc.summary.byMaterial.map(areaOf), 1);

  const regionsByMaterial = useMemo(() => {
    const map = new Map<number, Region[]>();
    for (const r of doc.regions) {
      const list = map.get(r.materialId) ?? [];
      list.push(r);
      map.set(r.materialId, list);
    }
    for (const list of map.values()) list.sort((a, b) => b.areaM2 - a.areaM2);
    return map;
  }, [doc]);

  // Recomputed here rather than taken from doc.summary, which the converter
  // wrote before the user had excluded anything.
  const totals = useMemo(() => {
    let included = 0;
    let removed = 0;
    let includedRegions = 0;
    const byCategory = new Map<string, { label: string; areaM2: number; regionCount: number }>();
    const add = (
      key: string, label: string, materialId: number, value: number,
    ) => {
      if (excluded.has(materialId)) {
        removed += value;
        return;
      }
      included += value;
      includedRegions++;
      const c = byCategory.get(key) ?? { label, areaM2: 0, regionCount: 0 };
      c.areaM2 += value;
      c.regionCount++;
      byCategory.set(key, c);
    };

    // Membership is read off the assemblies themselves rather than each
    // region's assemblyId: a model.json written by an older converter has no
    // assemblyId at all, and `undefined !== null` would skip every region and
    // silently total zero.
    const inAssembly = new Set(
      (doc.assemblies ?? []).flatMap((a) => a.regionIds),
    );
    for (const r of doc.regions) {
      // Battens of a screen are counted through their assembly, not one by one.
      if (inAssembly.has(r.id)) continue;
      add(r.category, r.categoryLabel, r.materialId, net ? r.exposedAreaM2 : r.areaM2);
    }
    for (const a of doc.assemblies ?? []) {
      add(a.category, a.categoryLabel, a.materialId, a.areaM2);
    }
    return {
      included,
      removed,
      includedRegions,
      byCategory: [...byCategory.entries()]
        .map(([category, v]) => ({ category, ...v }))
        .sort((a, b) => b.areaM2 - a.areaM2),
    };
  }, [doc, excluded, net]);

  const toggle = (id: number) => {
    const next = new Set(excluded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onExcludedChange(next);
  };

  // Rendered on the server: a browser-side PDF would have to ship a CJK font
  // in the bundle, and the report is entirely in Chinese.
  const exportPdf = async () => {
    setPdfOpen(false);
    setPdfBusy(true);
    setPdfError(null);
    try {
      const res = await fetch(`${projectBase(projectId)}/report.pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectName: reportMeta.projectName,
          site: reportMeta.site,
          excluded: [...excluded],
          net,
        }),
      });
      if (!res.ok) throw new Error(`伺服器回應 ${res.status}`);
      // A blob URL carries no headers, so the server's filename has to be read
      // off the response before the download is triggered.
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
      const name = encoded
        ? decodeURIComponent(encoded)
        : `${doc.source.modelName || "建材彙整"}.pdf`;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : String(e));
    } finally {
      setPdfBusy(false);
    }
  };

  const exportSummary = () =>
    downloadCsv(`${doc.source.modelName || "model"}_建材彙整.csv`, [
      ["材質", "材質類別", "計入", "全部面 (m2)", "扣除重疊 (m2)", "被埋沒 (m2)", "區塊數",
       ...totals.byCategory.map((c) => c.label + " (m2)")],
      ...doc.summary.byMaterial.map((row) => [
        row.name,
        materialCategory(doc.materials[row.materialId]) ?? "",
        excluded.has(row.materialId) ? "否" : "是",
        row.areaM2,
        row.exposedAreaM2,
        +(row.areaM2 - row.exposedAreaM2).toFixed(4),
        row.regionCount,
        ...totals.byCategory.map((c) => row.categories[c.category] ?? 0),
      ]),
      [],
      [`合計（計入者，${net ? "扣除重疊" : "全部面"}）`, "", "", "",
       totals.included.toFixed(2), "", totals.includedRegions],
      ["已排除", "", "", "", totals.removed.toFixed(2), "",
       doc.regions.length - totals.includedRegions],
      ["模型中被埋沒的面", "", "", "", "", doc.overlaps.hiddenM2.toFixed(2),
       `${doc.overlaps.pairCount} 組重疊`],
    ]);

  const exportDetail = () =>
    downloadCsv(`${doc.source.modelName || "model"}_建材明細.csv`, [
      ["區塊", "計入", "材質", "表面類型", "元件", "Tag", "形狀", "各邊長 (m)", "主要尺寸 (m)",
       "次要尺寸 (m)", "尺寸意義", "所屬格柵", "實心比例", "面積 (m2)", "被埋沒 (m2)",
       "扣除重疊 (m2)", "重疊對象", "中心X", "中心Y", "中心Z"],
      ...doc.regions.map((r) => [
        r.id,
        excluded.has(r.materialId) ? "否" : "是",
        doc.materials[r.materialId].name,
        r.categoryLabel,
        doc.elements[r.elementId]?.name ?? "",
        r.tag ?? "",
        SHAPE_LABEL[r.shape] ?? r.shape,
        r.edgesM.map((e) => e.toFixed(3)).join(" / "),
        r.lengthM,
        r.widthM,
        r.dimLabel,
        r.assemblyId === null
          ? ""
          : doc.assemblies?.find((a) => a.id === r.assemblyId)?.name ?? "",
        r.solidRatio,
        r.areaM2,
        r.hiddenM2,
        r.exposedAreaM2,
        r.overlapWith
          .map((o) => `${doc.elements[doc.regions[o.regionId].elementId]?.name ?? o.regionId}` +
                      `(${o.kind === "interface" ? "貼合" : "重複"} ${o.m2.toFixed(2)})`)
          .join(" / "),
        r.centroid[0],
        r.centroid[1],
        r.centroid[2],
      ]),
    ]);

  return (
    <div className="takeoff">
      <div className="takeoff-actions">
        <button className="primary" onClick={() => setPdfOpen(true)} disabled={pdfBusy}>
          {pdfBusy ? "產生中…" : "下載 PDF (A4)"}
        </button>
        <button onClick={exportSummary}>匯出彙整表 CSV</button>
        <button onClick={exportDetail}>匯出明細 CSV</button>
        {isolate !== null && (
          <button className="link" onClick={() => onIsolate(null)}>
            清除篩選
          </button>
        )}
      </div>
      {pdfError && <p className="err">PDF 產生失敗：{pdfError}</p>}

      {pdfOpen && (
        <ReportDialog
          value={reportMeta}
          basis={net ? "扣除重疊面" : "全部面"}
          excludedCount={excluded.size}
          onChange={updateMeta}
          onCancel={() => setPdfOpen(false)}
          onConfirm={exportPdf}
        />
      )}

      {doc.overlaps.pairCount > 0 && (
        <div className="mode-switch">
          <button className={net ? "" : "on"} onClick={() => onNetChange(false)}>
            全部面
          </button>
          <button className={net ? "on" : ""} onClick={() => onNetChange(true)}>
            扣除重疊
          </button>
        </div>
      )}

      <div className="total-card">
        <div>
          <span className="label">合計{net ? "（已扣除重疊）" : ""}</span>
          <span className="value">{area(totals.included)}</span>
        </div>
        {doc.overlaps.pairCount > 0 && (
          <p className="overlap-line">
            模型中有 {doc.overlaps.pairCount} 組重複表面、共 {area(doc.overlaps.hiddenM2)} 不計
            （{doc.overlaps.interfacePairs} 組量體貼合、{doc.overlaps.platePairs} 組薄板背面、
            {doc.overlaps.duplicatePairs} 組幾何重複）
          </p>
        )}
        {excluded.size > 0 ? (
          <p>
            已排除 {excluded.size} 種材質、{area(totals.removed)}
            <button className="link" onClick={() => onExcludedChange(new Set())}>
              全部計回
            </button>
          </p>
        ) : (
          <p>取消勾選即可把該材質排除在合計之外，模型中仍可點選查詢。</p>
        )}
      </div>

      {(doc.assemblies?.length ?? 0) > 0 && (
        <p className="note subtle">
          偵測到 {doc.assemblies.length} 組格柵，以<b>整片範圍</b>計算而非逐條加總：
          {doc.assemblies
            .map((a) => `${a.name}（${a.members} 支，${num(a.areaM2, 2)} m²，`
              + `逐面加總為 ${num(a.rawAreaM2, 2)} m²）`)
            .join("、")}
        </p>
      )}

      <h3>依材質</h3>
      <ul className="bars">
        {doc.summary.byMaterial.map((row) => {
          const material = doc.materials[row.materialId];
          const open = expanded === row.materialId;
          const off = excluded.has(row.materialId);
          const kind = materialCategory(material);
          return (
            <li
              key={row.materialId}
              className={
                (isolate === row.materialId ? "active" : "") + (off ? " excluded" : "")
              }
            >
              <div className="bar-row">
                <input
                  type="checkbox"
                  checked={!off}
                  title={off ? "計入合計" : "排除於合計之外"}
                  onChange={() => toggle(row.materialId)}
                />
                <span
                  className="swatch"
                  style={{
                    background: material.texture
                      ? `url(${projectBase(projectId)}/${material.texture}) center/cover`
                      : material.colorHex,
                  }}
                  onClick={() => onIsolate(isolate === row.materialId ? null : row.materialId)}
                />
                <span
                  className="bar-name"
                  title="點擊只顯示此材質"
                  onClick={() => onIsolate(isolate === row.materialId ? null : row.materialId)}
                >
                  {row.name}
                  {kind && <em className="bar-kind">{kind}</em>}
                </span>
                <span className="bar-value">{area(areaOf(row))}</span>
                <button
                  className="expand"
                  onClick={() => setExpanded(open ? null : row.materialId)}
                >
                  {open ? "▾" : "▸"} {row.regionCount}
                </button>
              </div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(areaOf(row) / maxArea) * 100}%` }} />
              </div>
              {open && (
                <ul className="sublist">
                  {(regionsByMaterial.get(row.materialId) ?? []).map((r) => (
                    <li key={r.id} onClick={() => onPickRegion(r.id)}>
                      <span className="sub-name">
                        {doc.elements[r.elementId]?.name ?? `區塊 ${r.id}`}
                      </span>
                      <span className="sub-dim">
                        {num(r.lengthM, 2)} × {num(r.widthM, 2)}
                      </span>
                      <span className="sub-area">{area(net ? r.exposedAreaM2 : r.areaM2)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <h3>依表面類型{excluded.size > 0 && "（已排除者不計）"}</h3>
      <table className="grid">
        <thead>
          <tr>
            <th>類型</th>
            <th className="r">面積</th>
            <th className="r">區塊數</th>
          </tr>
        </thead>
        <tbody>
          {totals.byCategory.map((row) => (
            <tr key={row.category}>
              <td>{row.label}</td>
              <td className="r">{area(row.areaM2)}</td>
              <td className="r">{row.regionCount}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// projects
// ---------------------------------------------------------------------------

export function ProjectList({
  projects,
  currentId,
  onOpen,
  onDelete,
}: {
  projects: Project[];
  currentId: string | null;
  onOpen: (p: Project) => void;
  onDelete: (p: Project) => void;
}) {
  if (!projects.length) {
    return <p className="hint">尚無專案，上傳一個 .skp 開始。</p>;
  }
  return (
    <ul className="projects">
      {projects.map((p) => (
        <li
          key={p.id}
          className={p.id === currentId ? "active" : ""}
          onClick={() => p.status === "ready" && onOpen(p)}
        >
          <div className="p-name">{p.name}</div>
          <div className="p-meta">
            {p.status === "ready" ? (
              <>
                {p.stats?.regions ?? 0} 區塊 · {p.materialCount ?? 0} 材質 · {bytes(p.sizeBytes)}
              </>
            ) : p.status === "error" ? (
              <span className="err">轉檔失敗</span>
            ) : (
              "轉檔中…"
            )}
          </div>
          <div className="p-date">{when(p.uploadedAt)}</div>
          <button
            className="del"
            title="刪除"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(p);
            }}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

export function Uploader({
  onUploaded,
  upload,
}: {
  onUploaded: (p: Project) => void;
  upload: (file: File, onProgress: (pct: number) => void) => Promise<Project>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const send = async (file: File) => {
    setBusy(true);
    setError(null);
    setPct(0);
    setPhase("上傳中");
    try {
      const project = await upload(file, (p) => {
        setPct(p);
        if (p >= 1) setPhase("解析模型中");
      });
      onUploaded(project);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setPhase("");
    }
  };

  return (
    <div
      className={`dropzone${dragging ? " over" : ""}${busy ? " busy" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files?.[0];
        if (file && !busy) send(file);
      }}
      onClick={() => !busy && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".skp"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) send(file);
          e.target.value = "";
        }}
      />
      {busy ? (
        <>
          <div className="progress">
            <div style={{ width: `${Math.round(pct * 100)}%` }} />
          </div>
          <span>
            {phase}
            {phase === "上傳中" ? ` ${Math.round(pct * 100)}%` : "…"}
          </span>
        </>
      ) : (
        <>
          <strong>拖入 .skp 檔案</strong>
          <span>或點擊選擇</span>
        </>
      )}
      {error && <p className="err">{error}</p>}
    </div>
  );
}
