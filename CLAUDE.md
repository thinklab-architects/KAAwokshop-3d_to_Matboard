# CLAUDE.md

給接手這份程式碼的 Claude。**先讀 `README.md`** —— 它把架構、量測規則、
重疊面偵測的原理都寫完了，這裡只補 README 沒講、但改動時會踩到的東西。

## 這是什麼

上傳 SketchUp `.skp` → 伺服器端解析 → 3D 檢視器中點選任一面，得到材質與長寬面積 →
匯出 PDF／CSV 建材彙整表。

```
converter/skp2web/   .skp → model.json + mesh.bin + textures/
  sdk.py             ctypes 綁定 SketchUpAPI.dll（唯一能讀 .skp 的途徑）
  extract.py         遍歷群組／元件，累積座標變換，解析材質繼承
  regions.py         合併同平面相鄰面 → 區塊，依輪廓形狀量長寬
  overlaps.py        重複表面偵測：共面貼合、薄板背面、重複幾何（三角形裁剪，精確面積）
  assemblies.py      成排板條 → 整片格柵，以立面範圍計算而非逐條加總
  emit.py            輸出 model.json 與 mesh.bin
server/app.py        FastAPI：上傳、轉檔、供檔，並掛載 web/dist
server/report.py     reportlab 產生中文 PDF
web/src/             React + three.js 檢視器
```

每個模組開頭都有一段 docstring 解釋「為什麼是這樣寫」。動任何一個檔案前先讀它。

## 環境需求：這件事沒有替代方案

`.skp` 是未公開格式，**沒有可靠的開源 parser**。`converter/skp2web/sdk.py` 用 ctypes
載入 SketchUp 的 `SketchUpAPI.dll`，而且是在 **import 時**（`sdk.py` 檔案結尾的
`lib, DLL_PATH = _load()`）。因此：

- **只能在 Windows 上跑**（官方 SDK 沒有 Linux 版）。Docker／Linux 容器不可行。
- **DLL 載不到時，`server/app.py` 整個 import 失敗**，伺服器起不來 —— 不是「功能少一項」
  而是「完全開不起來」。使用者若回報「網站打不開」，先查 `logs\server.err.log`。
- **不需要安裝 SketchUp，只需要那個 DLL。** `_candidate_dlls()` 的順序是
  `MATBOARD_SU_DLL` → `vendor/sketchup-sdk/` → 已安裝的 SketchUp，
  而 vendor 那份是 `insert(0)`，**優先於**已安裝的版本。發佈給沒有 SketchUp 的機器時，
  把官方 SDK 的 `SketchUpAPI.dll` 與 `SketchUpCommonPreferences.dll` 放進 `vendor/sketchup-sdk/` 即可。
  少了 `SketchUpCommonPreferences.dll` 會載入失敗（它在 `SketchUpAPI.dll` 的 import table 裡）。
- DLL 讀不了「太新」的 .skp。SketchUp 2022 的 DLL 實測可讀到檔案版本 23.1；
  換新版 SDK 的 DLL 就能讀更新的檔。

若真的需要讓沒有 SketchUp 的機器也能啟動網站（只看已轉好的專案），要改的是
`server/app.py` 頂端那行 `from skp2web import sdk` —— 包成 try/except 並在上傳端點
回報明確錯誤。**目前沒有這樣做**，別假設它有。

## 改動後要記得的事

| 改了什麼 | 一定要做 |
|---|---|
| `converter/` 任何檔案 | **重啟伺服器**，否則新上傳的模型仍走舊邏輯（已轉好的專案也不會自動重轉） |
| `web/src/` 任何檔案 | `cd web && npm run build` —— `web/dist` 是**已建置並納入版控**的，伺服器只讀 dist，不讀 src |
| `server/report.py` 版面 | 實際產一份 PDF 看，reportlab 的 flowable 高度算錯不會報錯，只會擠掉內容 |
| 量測或合併規則 | 跑 `converter/tests/`，並用 `samples/` 的模型對照 README 裡列出的實測數字 |

## 執行與測試

**這個資料夾自帶執行環境**：`runtime\`（官方 embeddable Python 3.12 ＋ 套件）與
`vendor\sketchup-sdk\`（DLL）。使用者只要雙擊 `開啟建材彙整.cmd`，不必安裝任何東西。
`tools\start.ps1` 找直譯器的順序是 `runtime\python.exe` → `.venv\Scripts\python.exe`。

下面的指令兩種環境都可以，把 `runtime\python.exe` 換成 `.venv\Scripts\python.exe` 即可。

```bash
runtime\python.exe -m uvicorn server.app:app --reload --port 8000
cd web && npm run dev                        # 前端熱重載，/api 自動代理到 8000
setup.cmd                                    # 只有要改用自己的 Python 才需要
```

`runtime\python312._pth` 已把 `..\converter` 加進 `sys.path`，所以用 `runtime\python.exe`
時不必 `cd converter`。**改了 `._pth` 要小心**：embeddable 版的 `sys.path` 完全由它決定，
目前目錄與 `PYTHONPATH` 都會被忽略。

```bash
runtime\python.exe -m tests.test_regions
runtime\python.exe -m tests.test_overlaps
runtime\python.exe -m tests.test_assemblies
```

命令列轉檔（除錯轉檔器時比走網站快得多）：

```bash
runtime\python.exe -m skp2web samples\Modern_House_Reference_02.skp -o out\
```

用 `.venv` 的話 `skp2web` 不在 path 上（`server/app.py` 是靠 `sys.path.insert` 把
`converter/` 加進來的），所以要 `cd converter`：

```bash
cd converter
..\.venv\Scripts\python.exe -m skp2web ..\samples\Modern_House_Reference_02.skp -o ..\out\
```

`samples/Modern_House_Reference_02.skp` 是專門為驗證而做的，幾何用腳本寫死產生，
所以**正確答案是已知的**。它涵蓋重疊面、薄板背面、格柵整片、多邊形輪廓、非建材排除；
改量測邏輯後拿它回歸比較，數字見 `samples/README.md`。

但它整個是軸向對齊的方盒，**開口扣除（`solidRatio` 全是 1.0）、旋轉樓板、斜屋頂坡長、
三角形量測在這個檔案上驗不到** —— 那幾條規則是 `converter/tests/` 用合成幾何涵蓋的。
別因為模型上看不到就以為壞了。

## 幾個容易誤判的設計決定

- **SDK 是行程全域狀態。** `SUInitialize`／`SUTerminate` 不可重入，所以 `app.py` 用
  `_convert_lock` 把轉檔序列化。不要拿掉，也不要改成多程序共用。
- **PDF 在伺服器端產。** 前端產就得把 CJK 字型打進 bundle，每次載入多背好幾 MB。
  字型從 `C:\Windows\Fonts` 找（`report.py`），找不到會退回 Helvetica ——
  版面撐得住，但中文會消失。
- **`mesh.bin` 不是 JSON。** 幾十萬頂點用 JSON 慢且大 5 倍。它是五段連續的 typed array
  （position／normal／uv／regionId／index），改格式必須同步改 `emit.py` 與 `web/src/model.ts`。
- **室內表面預設點不到**，因為被外殼擋住。檢視器的「水平剖面」同時作用於顯示與選取
  （three.js 的 raycaster 本身不理會 clipping plane，那是 `Viewer.tsx` 額外處理的）。
- **`storage/` 不入版控。** 每個人的模型留在自己機器上。示範檔在 `samples/`，要靠上傳。

## 語言

程式碼註解與 docstring 用英文，說明「為什麼」而不是「做什麼」。
使用者看得到的字串、README 與文件用**繁體中文**。沿用現有風格。
