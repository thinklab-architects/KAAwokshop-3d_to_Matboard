import { useEffect, useState, type ReactNode } from "react";

/** Horizontal arrow with a solid head, drawn inline so ids cannot collide. */
function Arrow({ x, y, len }: { x: number; y: number; len: number }) {
  return (
    <g className="f-arrow">
      <line x1={x} y1={y} x2={x + len - 6} y2={y} />
      <path d={`M${x + len} ${y} L${x + len - 7} ${y - 4} L${x + len - 7} ${y + 4} Z`} />
    </g>
  );
}

// ---------------------------------------------------------------------------
// figures
// ---------------------------------------------------------------------------

/** .skp goes in, a clickable model and a takeoff come out. */
function PipelineFigure() {
  const box = (x: number, w: number, title: string, sub: string) => (
    <g>
      <rect x={x} y={22} width={w} height={46} rx={5} className="f-box" />
      <text x={x + w / 2} y={42} className="f-lab strong">{title}</text>
      <text x={x + w / 2} y={56} className="f-lab">{sub}</text>
    </g>
  );
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 88" role="img" aria-label="上傳到解析到檢視的流程">
        {box(4, 108, ".skp 檔案", "你的 SketchUp 模型")}
        <Arrow x={120} y={45} len={38} />
        {box(162, 134, "伺服器解析", "取出材質・位置・尺寸")}
        <Arrow x={304} y={45} len={38} />
        {box(348, 128, "瀏覽器", "3D 預覽 + 建材彙整")}
        <text x={240} y={82} className="f-lab">
          解析在伺服器完成 —— 看網站的電腦不需要安裝 SketchUp
        </text>
      </svg>
    </figure>
  );
}

/** Drop a file on the left panel; it converts and joins the project list. */
function UploadFigure() {
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 112" role="img" aria-label="拖入檔案後出現在專案清單">
        {/* dropzone */}
        <g transform="translate(6,14)">
          <rect x="0" y="0" width="132" height="52" rx="6" className="f-cutaway" />
          <text x="66" y="24" className="f-lab strong">拖入 .skp 檔案</text>
          <text x="66" y="38" className="f-lab">或點擊選擇</text>
          {/* the file being dragged in */}
          <g transform="translate(96,-10)">
            <path d="M0 0 L14 0 L20 6 L20 24 L0 24 Z" className="f-fill" />
            <path d="M14 0 L14 6 L20 6" className="f-hair" />
          </g>
        </g>
        <Arrow x={146} y={40} len={30} />

        {/* project list */}
        <g transform="translate(186,6)">
          <text x="0" y="6" className="f-lab" textAnchor="start">專案</text>
          {[0, 1].map((n) => (
            <g key={n} transform={`translate(0,${12 + n * 26})`}>
              <rect x="0" y="0" width="132" height="22" rx="4"
                    className={n === 0 ? "f-fill" : "f-box"} />
              <text x="8" y="10" className="f-txt tiny">住宅案_模型.skp</text>
              <text x="8" y="19" className="f-txt tiny muted">890 區塊 · 13 材質</text>
            </g>
          ))}
        </g>

        <line x1="336" y1="8" x2="336" y2="104" className="f-hair" />
        <text x="350" y="24" className="f-txt">上傳後自動解析並開啟。</text>
        <text x="350" y="42" className="f-txt">已上傳的留在清單裡，</text>
        <text x="350" y="56" className="f-txt">隨時切換不必重傳。</text>
        <text x="350" y="80" className="f-txt">關閉的圖層（Tag）</text>
        <text x="350" y="94" className="f-txt">預設不納入。</text>
      </svg>
    </figure>
  );
}

/** The three-button mouse, since that is what the navigation is bound to. */
function MouseFigure() {
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 132" role="img" aria-label="滑鼠操作對照">
        {/* mouse body */}
        <g transform="translate(28,14)">
          <rect x="0" y="0" width="70" height="104" rx="34" className="f-box" />
          <path d="M35 0 L35 40" className="f-hair" />
          <path d="M0 40 L70 40" className="f-hair" />
          <rect x="27" y="6" width="16" height="30" rx="8" className="f-fill" />
          <path d="M35 12 L35 30" className="f-hair" />
        </g>
        <line x1="106" y1="35" x2="150" y2="35" className="f-lead" />
        <line x1="106" y1="70" x2="150" y2="70" className="f-lead" />
        <line x1="106" y1="100" x2="150" y2="100" className="f-lead" />

        <text x="158" y="26" className="f-txt strong">中鍵拖曳</text>
        <text x="158" y="40" className="f-txt">旋轉視角</text>
        <text x="158" y="64" className="f-txt strong">Shift + 中鍵拖曳</text>
        <text x="158" y="78" className="f-txt">平移</text>
        <text x="158" y="102" className="f-txt strong">滾輪</text>
        <text x="158" y="116" className="f-txt">縮放，往游標所在位置</text>

        <line x1="320" y1="14" x2="320" y2="118" className="f-hair" />
        <text x="336" y="26" className="f-txt strong">左鍵點擊</text>
        <text x="336" y="40" className="f-txt">選取一個面</text>
        <text x="336" y="64" className="f-txt strong">Shift + Z</text>
        <text x="336" y="78" className="f-txt">顯示全部</text>
        <text x="336" y="102" className="f-txt">沒有中鍵時：左鍵拖曳</text>
        <text x="336" y="116" className="f-txt">也可旋轉，右鍵拖曳平移</text>
      </svg>
    </figure>
  );
}

/** Click a face, its data appears beside it. */
function PickFigure() {
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 128" role="img" aria-label="點選面後右側顯示資料">
        {/* massing */}
        <g transform="translate(18,16)">
          <path d="M0 90 L0 34 L58 8 L128 30 L128 86 L62 108 Z" className="f-box" />
          <path d="M0 34 L62 56 L128 30" className="f-hair" />
          <path d="M62 56 L62 108" className="f-hair" />
          <path d="M0 34 L58 8 L128 30 L62 56 Z" className="f-fill" />
          {/* the picked face */}
          <path d="M62 56 L128 30 L128 86 L62 108 Z" className="f-pick" />
        </g>
        {/* cursor */}
        <path d="M126 92 L126 110 L131 105 L135 114 L139 112 L135 103 L142 103 Z" className="f-cursor" />

        <Arrow x={172} y={62} len={30} />

        {/* panel */}
        <g transform="translate(212,10)">
          <rect x="0" y="0" width="252" height="108" rx="5" className="f-box" />
          <rect x="10" y="10" width="22" height="22" rx="4" className="f-pick" />
          <text x="40" y="20" className="f-txt strong">白色磁磚</text>
          <text x="40" y="32" className="f-txt">牆面 · Tag 02_White-Tile</text>
          <line x1="10" y1="42" x2="242" y2="42" className="f-hair" />
          <text x="10" y="58" className="f-txt">面積</text>
          <text x="86" y="58" className="f-txt strong">8.64 m²</text>
          <text x="10" y="74" className="f-txt">寬 × 高</text>
          <text x="86" y="74" className="f-txt strong">3.200 × 2.700 m</text>
          <text x="10" y="90" className="f-txt">朝向</text>
          <text x="86" y="90" className="f-txt strong">朝東</text>
          <text x="10" y="104" className="f-txt">高程</text>
          <text x="86" y="104" className="f-txt strong">+4.05 ~ +6.75 m</text>
        </g>
      </svg>
    </figure>
  );
}

/** One figure per branch of the measurement: rectangle, triangle, anything else. */
function MeasureFigures() {
  return (
    <div className="g-figs">
      <figure>
        <svg viewBox="0 0 120 92" role="img" aria-label="矩形報兩個邊長">
          <rect x="22" y="16" width="76" height="54" className="f-face" />
          <text x="60" y="12" className="f-lab">4.20</text>
          <text x="106" y="46" className="f-lab">2.70</text>
          <line x1="22" y1="79" x2="98" y2="79" className="f-dim" />
          <line x1="14" y1="16" x2="14" y2="70" className="f-dim" />
          <text x="60" y="89" className="f-lab">寬</text>
          <text x="7" y="46" className="f-lab">高</text>
        </svg>
        <figcaption>
          <b>矩形</b>報它自己的兩個邊長。牆面依立面習慣排成寬 × 高
        </figcaption>
      </figure>
      <figure>
        <svg viewBox="0 0 120 92" role="img" aria-label="三角形報三個邊長">
          <path d="M18 72 L102 72 L66 20 Z" className="f-face" />
          <text x="58" y="85" className="f-lab">c</text>
          <text x="88" y="44" className="f-lab">a</text>
          <text x="36" y="44" className="f-lab">b</text>
        </svg>
        <figcaption>
          <b>三角形</b>報三個邊長，面積用三角形本身算
        </figcaption>
      </figure>
      <figure>
        <svg viewBox="0 0 120 92" role="img" aria-label="其他形狀逐段報邊長">
          <path d="M25 20 L65 20 L65 46 L98 46 L98 74 L25 74 Z" className="f-face" />
          <text x="45" y="15" className="f-lab">1</text>
          <text x="72" y="36" className="f-lab">2</text>
          <text x="82" y="42" className="f-lab">3</text>
          <text x="106" y="63" className="f-lab">4</text>
          <text x="60" y="85" className="f-lab">5</text>
          <text x="18" y="50" className="f-lab">6</text>
        </svg>
        <figcaption>
          <b>其他形狀</b>逐段列出每一條邊長
        </figcaption>
      </figure>
    </div>
  );
}

/** Why the interior cannot be clicked, and what the section does about it. */
function SectionFigure() {
  const house = (dx: number, cut: boolean) => (
    <g transform={`translate(${dx},18)`}>
      {!cut && <path d="M6 22 L98 22 L98 34 L6 34 Z" className="f-solid" />}
      {cut && <path d="M6 22 L98 22 L98 34 L6 34 Z" className="f-cutaway" />}
      <path d="M6 34 L6 96 L98 96 L98 34" className="f-box" />
      <path d="M18 72 L86 72 L86 80 L18 80 Z" className="f-pick" />
      <text x="52" y="92" className="f-lab">室內樓板</text>
      {cut && <line x1="0" y1="40" x2="104" y2="40" className="f-cut" />}
      {/* the ray */}
      <path
        d={cut ? "M52 -14 L52 66" : "M52 -14 L52 18"}
        className="f-ray"
      />
      <path
        d={cut ? "M52 70 L48 62 L56 62 Z" : "M52 22 L48 14 L56 14 Z"}
        className="f-ray-head"
      />
    </g>
  );
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 132" role="img" aria-label="剖面前後的差別">
        {house(48, false)}
        <text x="100" y="128" className="f-lab">剖面關閉 —— 射線打到屋頂就停了</text>
        <line x1="240" y1="10" x2="240" y2="120" className="f-hair" />
        {house(302, true)}
        <text x="354" y="128" className="f-lab">剖面開啟 —— 屋頂被切掉，樓板可點選</text>
      </svg>
    </figure>
  );
}

/** The takeoff row, and what unticking one does. */
function TakeoffFigure() {
  const row = (
    y: number, name: string, area: string, w: number, off: boolean,
  ) => (
    <g transform={`translate(0,${y})`}>
      <rect x="2" y="2" width="11" height="11" rx="2" className={off ? "f-box" : "f-checked"} />
      {!off && <path d="M4.5 7.5 L6.8 10 L11 4.5" className="f-tick" />}
      <rect x="20" y="1" width="13" height="13" rx="3" className="f-fill" />
      <text x="40" y="12" className={off ? "f-txt muted" : "f-txt"}>{name}</text>
      <text x="232" y="12" className={off ? "f-txt muted end" : "f-txt end"}>{area}</text>
      <rect x="40" y="18" width="192" height="3" rx="1.5" className="f-track" />
      <rect x="40" y="18" width={w} height="3" rx="1.5" className={off ? "f-track" : "f-bar"} />
    </g>
  );
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 118" role="img" aria-label="彙整表的勾選與排除">
        <g transform="translate(10,8)">
          {row(0, "白色磁磚", "753.06 m²", 150, false)}
          {row(30, "清水混凝土", "999.52 m²", 192, false)}
          {row(60, "室內陰影", "484.07 m²", 96, true)}
        </g>
        <line x1="258" y1="8" x2="258" y2="102" className="f-hair" />
        <text x="272" y="30" className="f-txt strong">取消勾選 = 不計入合計</text>
        <text x="272" y="46" className="f-txt">模型裡常有不是建材的東西，</text>
        <text x="272" y="60" className="f-txt">例如玻璃後方的暗色襯底。</text>
        <text x="272" y="80" className="f-txt">排除後合計會重算，</text>
        <text x="272" y="94" className="f-txt">它在 3D 中仍可點選查詢。</text>
      </svg>
    </figure>
  );
}

/** What the exported sheet looks like. */
function PdfFigure() {
  const band = (y: number, cols: number) => (
    <g transform={`translate(0,${y})`}>
      <rect x="0" y="0" width="230" height="62" className="f-sheet" />
      <line x1="0" y1="9" x2="230" y2="9" className="f-hair" />
      <line x1="36" y1="0" x2="36" y2="62" className="f-hair" />
      {Array.from({ length: 5 }, (_, i) => (
        <line key={i} x1="0" y1={9 + 30 + i * 6} x2="230" y2={9 + 30 + i * 6} className="f-hair" />
      ))}
      {Array.from({ length: cols }, (_, i) => (
        <g key={i}>
          <line x1={36 + (i + 1) * 27.6} y1="0" x2={36 + (i + 1) * 27.6} y2="62" className="f-hair" />
          <rect x={36 + i * 27.6 + 6} y="13" width="15" height="15" className="f-fill" />
        </g>
      ))}
    </g>
  );
  return (
    <figure className="g-fig">
      <svg viewBox="0 0 480 158" role="img" aria-label="匯出的 A4 橫式建材彙整表">
        <g transform="translate(8,6)">
          <rect x="-4" y="-4" width="238" height="150" rx="3" className="f-box" />
          <text x="0" y="8" className="f-txt strong tiny">建材彙整表</text>
          <line x1="0" y1="12" x2="230" y2="12" className="f-rule" />
          {band(20, 7)}
          {band(88, 4)}
          <rect x="0" y="134" width="230" height="8" className="f-sheet" />
        </g>
        <text x="124" y="156" className="f-lab">A4 橫式・一頁兩帶</text>

        <line x1="258" y1="6" x2="258" y2="150" className="f-hair" />
        <text x="272" y="20" className="f-txt strong">材質成欄、屬性成列</text>
        <text x="272" y="34" className="f-txt">與門窗表相同的讀法。欄頂放材質圖示，</text>
        <text x="272" y="48" className="f-txt">下方依序是名稱、類別、貼圖單元、</text>
        <text x="272" y="62" className="f-txt">主要用於、區塊數與面積。</text>
        <text x="272" y="86" className="f-txt strong">產生前會先問專案名稱與基地</text>
        <text x="272" y="100" className="f-txt">會印在抬頭，並記住供下次使用。</text>
        <text x="272" y="120" className="f-txt strong">只列出有勾選的材質</text>
        <text x="272" y="134" className="f-txt">被排除的不會出現在表格中，</text>
        <text x="272" y="148" className="f-txt">但抬頭會記錄排除了哪些、共多少。</text>
      </svg>
    </figure>
  );
}

// ---------------------------------------------------------------------------

interface Slide {
  title: string;
  lead: string;
  body: ReactNode;
}

const SLIDES: Slide[] = [
  {
    title: "這個網站在做什麼",
    lead: "上傳 SketchUp 模型，點選任一面就看到它的材質與尺寸。",
    body: (
      <>
        <PipelineFigure />
        <ul className="g-list">
          <li>牆面、地板、天花、屋頂會自動分類</li>
          <li>被邊線切碎的同一面牆會自動合併回一整片</li>
          <li>模型自帶的屬性（例如 <code>BIM_Data</code>）會原樣帶出</li>
        </ul>
      </>
    ),
  },
  {
    title: "上傳模型",
    lead: "把 .skp 拖進左上角，或點一下選檔。",
    body: (
      <>
        <UploadFigure />
        <ul className="g-list">
          <li>關閉的圖層（Tag）預設不納入，讓數量與模型看到的一致</li>
          <li>解析失敗會說明原因，例如檔案毀損或 SketchUp 版本太新</li>
          <li>清單項目右上角的 <b>×</b> 可刪除專案</li>
        </ul>
      </>
    ),
  },
  {
    title: "轉動視角",
    lead: "沿用 SketchUp 的操作習慣。",
    body: <MouseFigure />,
  },
  {
    title: "點選查詢",
    lead: "點模型上任何一面，右側「選取面」就會顯示它的資料。",
    body: (
      <>
        <PickFigure />
        <p className="g-note">
          <b>面積</b>由三角形實算、開口已扣除；<b>朝向</b>由法線換算成方位；
          <b>高程</b>是這一面所在的標高範圍。下方「模型自帶屬性」與「幾何細節」
          預設收合，需要時再展開。
        </p>
      </>
    ),
  },
  {
    title: "尺寸是怎麼量的",
    lead: "量的是這個面實際的輪廓，不是外面套一個框。",
    body: (
      <>
        <MeasureFigures />
        <p className="g-note">
          <b>轉了角度也一樣。</b>6 × 4 m 的樓板轉 30°，報的仍是 6.00 與 4.00，
          因為量的是它自己的邊。面積一律由三角形實算，跟形狀判斷無關；
          若面上有開口，會顯示扣除後的比例。
        </p>
      </>
    ),
  },
  {
    title: "看不到的表面，用剖面取出",
    lead: "室內樓板、天花被不透明的屋頂擋住，點不到。",
    body: (
      <>
        <SectionFigure />
        <p className="g-note">
          點選是用射線打向模型，只會打中最前面的那一層。勾選檢視區
          <b>右上角的「水平剖面」</b>，拉動滑桿由上往下剖切，室內就露出來了 ——
          被剖掉的部分同時不再阻擋點選。剖切面為空心（不填實），與 SketchUp 的預設行為一致。
        </p>
      </>
    ),
  },
  {
    title: "建材彙整",
    lead: "右側切到「建材彙整」分頁，看整份模型的材料統計。",
    body: (
      <>
        <TakeoffFigure />
        <ul className="g-list">
          <li>材質名稱下方會顯示模型自己記的<b>材質類別</b>，可用來判斷該不該排除</li>
          <li>
            <b>格柵以整片計算</b>：一片木格柵是二十根獨立板條，逐條加總會得到
            「二十根棍子的表面積」。系統會偵測出成排的板條，改以整片立面範圍計算
            （柱列不會被誤判 —— 判斷依據是間距相對板寬很小）
          </li>
          <li><b>點材質名稱</b>：只顯示該材質，其餘淡出；再點一次取消</li>
          <li>
            <b>全部面／扣除重疊</b>：切到「扣除重疊」會扣掉三種重複計算 ——
            量體貼合的接觸面（兩側都看不見）、<b>薄板的背面</b>（樓板底面、玻璃背面，
            面材只鋪一次）、以及被畫了兩次的幾何。牆不算薄板，兩側都會保留
          </li>
        </ul>
      </>
    ),
  },
  {
    title: "匯出",
    lead: "一份 A4 橫式 PDF，加上兩種 CSV。",
    body: (
      <>
        <PdfFigure />
        <p className="g-note">
          <b>彙整表 CSV</b> 為各材質總面積，<b>明細 CSV</b> 為逐區塊的形狀、各邊長、
          面積與座標。三種匯出都會套用當下的排除設定與「全部面／扣除重疊」選擇。
        </p>
      </>
    ),
  },
];

export default function Guide({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const last = SLIDES.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") setI((n) => Math.min(n + 1, last));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(n - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, last]);

  const slide = SLIDES[i];
  return (
    <div className="g-backdrop" onClick={onClose}>
      <div
        className="g-modal"
        role="dialog"
        aria-modal="true"
        aria-label="使用說明"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="g-head">
          <span className="g-step">
            {i + 1} / {SLIDES.length}
          </span>
          <h2>{slide.title}</h2>
          <button className="g-close" onClick={onClose} aria-label="關閉">
            ×
          </button>
        </header>

        <div className="g-body" key={i}>
          <p className="g-lead">{slide.lead}</p>
          {slide.body}
        </div>

        <footer className="g-foot">
          <button onClick={() => setI(i - 1)} disabled={i === 0}>
            上一頁
          </button>
          <div className="g-dots">
            {SLIDES.map((s, n) => (
              <button
                key={s.title}
                className={n === i ? "on" : ""}
                onClick={() => setI(n)}
                aria-label={`第 ${n + 1} 頁：${s.title}`}
              />
            ))}
          </div>
          {i === last ? (
            <button className="primary" onClick={onClose}>
              開始使用
            </button>
          ) : (
            <button className="primary" onClick={() => setI(i + 1)}>
              下一頁
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
