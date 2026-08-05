# 現代住宅參考模型 02

第二個現代風格住宅研究，與 `Modern_House_Reference_01` 使用相同的製作慣例（公制、`MAT-NN` 材料鍵、編號 Tag、Attribute Dictionary、具名場景），但量體構想不同，並改以 `./textures` 內的點陣貼圖驅動所有主要飾面。

## 設計構想

- 西側一座整體式清水模量體貫穿兩層，中央開一道 0.60 × 5.20 m 的全高玻璃縫。
- 白色磁磚二樓量體向前懸挑 **2.00 m**，覆蓋在全面開窗的一樓之上，形成入口遮蔭。
- 二樓西半為起居開窗，東半以雪松格柵過濾臥室採光；格柵後方為深色煙燻玻璃。兩處開口是自白磚實牆上開孔（壁柱 `Upper_Front_Wall_Pier_*`、腰牆 `_Spandrel`、楣樑 `_Head`），窗框較牆面凸出 10 mm。
- 一樓入口為齊平雪松門扇，四周留 30 mm 陰影縫。
- 前庭配置鏡面水池、石材平台與植槽。

## 模型尺寸

- 建築總寬：14.000 m
- 建築總深：12.600 m（含 2.000 m 懸挑）
- 建築總高：7.100 m
- 一樓完成面：+0.450 m
- 二樓結構面／一樓頂：+3.750 m
- 女兒牆頂：+7.050 m
- 一樓室內面積：約 91.8 m²

正立面朝 **-Y（南）**。側面與背面為合理化概念量體，不應視為施工圖或現況資料。

## 材料命名

貼圖取自 `I:\webapp workshop\CW\textures`，六張全數使用；玻璃、框料、陰影與水面無對應貼圖，以純色處理。

材質名稱直接使用中文飾面名稱，方便在材料面板與 Entity Info 辨識；原本的 `MAT-NN` 代碼保留在屬性字典的 `Legacy_Key` 供對照。

| 材質名稱 | 用於 | 貼圖 | 貼圖尺寸 | Legacy_Key |
|---|---|---|---|---|
| **白色磁磚** | 二樓量體、一樓端牆 | `wall_tile_white.png` | 600 mm | MAT-01 |
| **清水混凝土** | 西側量體、樓板、平台、植槽 | `wall_concrete_grey.png` | 1200 mm | MAT-02 |
| **木飾板** | 格柵、入口牆與門、樹幹 | `wall_wood_cedar.png` | 800 mm | MAT-03 |
| **金屬屋面** | 屋頂覆蓋 | `roof_metal_darkgrey.png` | 900 mm | MAT-04 |
| **橡木地板** | 室內地板（透過玻璃可見） | `floor_wood_oak.png` | 1200 mm | MAT-05 |
| **草地** | 基地草皮 | `site_grass_green.png` | 2000 mm | MAT-06 |
| **清玻璃** | 外牆開窗 | 純色 α0.38 | — | MAT-07 |
| **煙燻玻璃** | 格柵背板 | 純色 α0.55 | — | MAT-08 |
| **深色鋁框** | 門窗框料、門把 | 純色 | — | MAT-09 |
| **室內陰影** | 室內視覺背景 | 純色 | — | MAT-10 |
| **水池** | 鏡面水池水面 | 純色 α0.78 | — | MAT-11 |
| **植栽** | 概念灌木與樹冠 | 純色 | — | MAT-12 |

每個材料的 `Material_Specification` 字典內含 `Category`、`Colour`、`Finish`、`Module`、`Texture_File`、`Texture_Size_mm`、`Material_Key`、`Legacy_Key`。模型只保留這 12 個材質，範本殘留（如預設的「材料」）會在產生時清除。

## 模型組織

- `00_Site-and-Paving`
- `01_Building-Massing`
- `02_White-Tile-Cladding`
- `03_Concrete-Elements`
- `04_Glazing`
- `05_Timber-Screen-and-Door`
- `06_Metal-Framing`
- `07_Landscape`
- `08_Reference-Dimensions`（預設關閉）

共 86 個群組，每個群組帶 `BIM_Data` 字典：`Element_Name`、`Width_m`、`Depth_m`、`Height_m`、`Origin_m`、`Material_Key`、`Tag`，開口另有 `Assembly`、`Component`、`Panels`、`Glass_Area_m2`。模型層另有 `Project_Information` 字典記錄總尺寸、樓層高、懸挑長度與貼圖庫路徑。

查詢範例（Ruby Console）：

```ruby
Sketchup.active_model.entities.grep(Sketchup::Group).each do |g|
  d = g.attribute_dictionary('BIM_Data')
  puts "#{g.name}\t#{d['Material_Key']}\t#{d['Tag']}" if d
end
```

模型包含三個場景：

- `01_Front_Perspective`
- `02_Front_Orthographic`
- `03_Site_Aerial`

## 輸出檔案

- `output/Modern_House_Reference_02.skp`
- `output/Modern_House_Reference_02_preview.png`
- `output/Modern_House_Reference_02_build.log`

## 重新生成

在 SketchUp 的 Ruby Console 執行：

```ruby
load 'I:/webapp workshop/CW/generate_modern_house_02.rb'
```

腳本會清空當前開啟模型，請先另存任何尚未保存的工作。與 01 的腳本不同，本腳本**不會**自動關閉 SketchUp；結果字串會存入 `$MODERN_HOUSE_02`。

## 已知事項

- 樹木為 `07_Landscape` 上的概念量體（分層圓柱），非寫實植栽；不需要時可關閉該 Tag。
- 側面與背面開口未依實際平面配置，僅維持量體完整性。
