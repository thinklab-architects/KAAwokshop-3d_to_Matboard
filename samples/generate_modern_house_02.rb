# frozen_string_literal: true
# encoding: UTF-8

# SketchUp Ruby generation script - Modern House Reference 02
# A second, independent modern-house study. Same authoring conventions as
# generate_modern_house.rb (metric, MAT-NN material keys, numbered tags,
# attribute dictionaries, named scenes) but a different architectural parti:
#
#   A solid board-formed concrete tower with a full-height glazed slot,
#   against a white ceramic-tile upper volume that cantilevers 2.0 m over a
#   fully glazed ground floor. Cedar screening filters the west bedrooms.
#
# Surface finishes are driven by the bitmap textures in ./textures.
#
# Usage (SketchUp Ruby Console):
#   load 'I:/webapp workshop/CW/generate_modern_house_02.rb'
#
# WARNING: the script clears the currently open model. Save your work first.

require 'sketchup.rb'
require 'fileutils'

module ModernHouse02
  extend self

  ROOT = File.expand_path(File.dirname(__FILE__))
  TEXTURE_DIR = File.join(ROOT, 'textures')
  OUTPUT_DIR = File.join(ROOT, 'output')
  SKP_PATH = File.join(OUTPUT_DIR, 'Modern_House_Reference_02.skp')
  PNG_PATH = File.join(OUTPUT_DIR, 'Modern_House_Reference_02_preview.png')
  LOG_PATH = File.join(OUTPUT_DIR, 'Modern_House_Reference_02_build.log')

  WIDTH = 14.0        # overall building width  (X)
  DEPTH = 12.6        # overall building depth  (Y, incl. 2.0 m cantilever)
  FFL = 0.45          # ground floor finished level
  L2 = 3.75           # top of ground floor / underside of upper slab
  TOP = 7.05          # parapet top
  CANTILEVER = 2.00   # upper volume projection beyond the ground floor face

  def m(value)
    value.to_f.m
  end

  def point(x, y, z)
    Geom::Point3d.new(m(x), m(y), m(z))
  end

  def vector(x, y, z)
    Geom::Vector3d.new(m(x), m(y), m(z))
  end

  # --------------------------------------------------------------- materials
  def ensure_material(model, name, rgb, alpha, metadata, texture = nil, texture_size_m = nil)
    material = model.materials[name] || model.materials.add(name)
    path = texture ? File.join(TEXTURE_DIR, texture) : nil
    if path && File.exist?(path)
      material.texture = path
      begin
        material.texture.size = [m(texture_size_m), m(texture_size_m)]
      rescue StandardError
        material.texture.size = m(texture_size_m)
      end
      metadata = metadata.merge(
        'Texture_File' => texture,
        'Texture_Size_mm' => (texture_size_m * 1000).round,
        'Texture_Source' => 'bitmap'
      )
    else
      material.color = Sketchup::Color.new(*rgb)
      metadata = metadata.merge('Texture_Source' => 'solid colour')
    end
    material.alpha = alpha
    metadata.each { |key, value| material.set_attribute('Material_Specification', key, value) }
    material.set_attribute('Material_Specification', 'Material_Key', name)
    material
  end

  def ensure_tag(model, name, visible = true)
    tag = model.layers[name] || model.layers.add(name)
    tag.visible = visible
    tag
  end

  # ---------------------------------------------------------------- geometry
  def add_box(parent_entities, name, x, y, z, dx, dy, dz, material, tag, data = {})
    group = parent_entities.add_group
    group.name = name
    group.layer = tag if tag
    face = group.entities.add_face(
      point(x, y, z), point(x + dx, y, z), point(x + dx, y + dy, z), point(x, y + dy, z)
    )
    face.reverse! if face.normal.z < 0
    face.pushpull(m(dz))
    group.material = material if material
    group.set_attribute('BIM_Data', 'Element_Name', name)
    group.set_attribute('BIM_Data', 'Width_m', dx.round(3))
    group.set_attribute('BIM_Data', 'Depth_m', dy.round(3))
    group.set_attribute('BIM_Data', 'Height_m', dz.round(3))
    group.set_attribute('BIM_Data', 'Origin_m', [x.round(3), y.round(3), z.round(3)])
    group.set_attribute('BIM_Data', 'Material_Key', material ? material.name : '')
    group.set_attribute('BIM_Data', 'Tag', tag ? tag.name : '')
    data.each { |key, value| group.set_attribute('BIM_Data', key, value) }
    group
  end

  def add_cylinder(parent_entities, name, cx, cy, z, radius, height, sides, material, tag)
    group = parent_entities.add_group
    group.name = name
    group.layer = tag if tag
    edges = group.entities.add_circle(point(cx, cy, z), Z_AXIS, m(radius), sides)
    face = group.entities.add_face(edges)
    face.reverse! if face.normal.z < 0
    face.pushpull(m(height))
    group.material = material if material
    group.set_attribute('BIM_Data', 'Element_Name', name)
    group.set_attribute('BIM_Data', 'Radius_m', radius)
    group.set_attribute('BIM_Data', 'Height_m', height)
    group.set_attribute('BIM_Data', 'Material_Key', material ? material.name : '')
    group
  end

  # SketchUp's default projection lands the bitmap 90 degrees out on vertical
  # faces, which matters for directional finishes such as the cedar boards.
  # Re-map so the image U axis follows the horizontal edge of each face.
  def vertical_grain!(group, material, tile_m)
    step = m(tile_m)
    group.entities.grep(Sketchup::Face).each do |face|
      normal = face.normal
      next if normal.z.abs > 0.7
      base = face.vertices.map(&:position).min_by do |p|
        [p.z.to_f.round(4), p.x.to_f.round(4), p.y.to_f.round(4)]
      end
      direction = if normal.x.abs > normal.y.abs
                    Geom::Vector3d.new(0, step, 0)
                  else
                    Geom::Vector3d.new(step, 0, 0)
                  end
      mapping = [base, Geom::Point3d.new(0, 0, 0),
                 base.offset(direction), Geom::Point3d.new(1, 0, 0)]
      face.position_material(material, mapping, true)
      face.position_material(material, mapping, false)
    end
    group
  end

  # ------------------------------------------------------------- assemblies
  def add_glazing(entities, name, x0, x1, y, z0, z1, panels, glass, frame, glass_tag, metal_tag)
    width = x1 - x0
    height = z1 - z0
    add_box(entities, "#{name}_Glass", x0, y, z0, width, 0.030, height, glass, glass_tag,
            'Assembly' => name, 'Component' => 'glass', 'Panels' => panels,
            'Glass_Area_m2' => (width * height).round(2))
    f = 0.060
    add_box(entities, "#{name}_Frame_Left", x0 - f, y - 0.050, z0, f, 0.070, height, frame, metal_tag,
            'Assembly' => name, 'Component' => 'jamb')
    add_box(entities, "#{name}_Frame_Right", x1, y - 0.050, z0, f, 0.070, height, frame, metal_tag,
            'Assembly' => name, 'Component' => 'jamb')
    add_box(entities, "#{name}_Frame_Sill", x0 - f, y - 0.050, z0 - f, width + 2 * f, 0.070, f,
            frame, metal_tag, 'Assembly' => name, 'Component' => 'sill')
    add_box(entities, "#{name}_Frame_Head", x0 - f, y - 0.050, z1, width + 2 * f, 0.070, f,
            frame, metal_tag, 'Assembly' => name, 'Component' => 'head')
    (1...panels).each do |index|
      x = x0 + width * index / panels
      add_box(entities, format('%s_Mullion_%02d', name, index), x - 0.027, y - 0.045, z0,
              0.054, 0.062, height, frame, metal_tag,
              'Assembly' => name, 'Component' => 'mullion')
    end
  end

  # Same assembly rotated onto a face whose normal is +X (east elevation).
  def add_glazing_east(entities, name, y0, y1, x, z0, z1, panels, glass, frame, glass_tag, metal_tag)
    width = y1 - y0
    height = z1 - z0
    add_box(entities, "#{name}_Glass", x - 0.030, y0, z0, 0.030, width, height, glass, glass_tag,
            'Assembly' => name, 'Component' => 'glass', 'Panels' => panels,
            'Glass_Area_m2' => (width * height).round(2))
    f = 0.060
    add_box(entities, "#{name}_Frame_South", x - 0.050, y0 - f, z0, 0.070, f, height, frame, metal_tag,
            'Assembly' => name, 'Component' => 'jamb')
    add_box(entities, "#{name}_Frame_North", x - 0.050, y1, z0, 0.070, f, height, frame, metal_tag,
            'Assembly' => name, 'Component' => 'jamb')
    add_box(entities, "#{name}_Frame_Sill", x - 0.050, y0 - f, z0 - f, 0.070, width + 2 * f, f,
            frame, metal_tag, 'Assembly' => name, 'Component' => 'sill')
    add_box(entities, "#{name}_Frame_Head", x - 0.050, y0 - f, z1, 0.070, width + 2 * f, f,
            frame, metal_tag, 'Assembly' => name, 'Component' => 'head')
    (1...panels).each do |index|
      y = y0 + width * index / panels
      add_box(entities, format('%s_Mullion_%02d', name, index), x - 0.045, y - 0.027, z0,
              0.062, 0.054, height, frame, metal_tag,
              'Assembly' => name, 'Component' => 'mullion')
    end
  end

  def add_timber_screen(entities, name, x0, x1, y, z0, z1, timber, dark_glass, wood_tag, glass_tag)
    width = x1 - x0
    height = z1 - z0
    add_box(entities, "#{name}_Smoked_Glass_Backing", x0, y + 0.120, z0, width, 0.028, height,
            dark_glass, glass_tag, 'Assembly' => name, 'Component' => 'backing glazing')

    screen = entities.add_group
    screen.name = name
    screen.layer = wood_tag
    screen.set_attribute('BIM_Data', 'Element_Name', name)
    screen.set_attribute('BIM_Data', 'Overall_Width_m', width.round(3))
    screen.set_attribute('BIM_Data', 'Overall_Height_m', height.round(3))
    screen.set_attribute('BIM_Data', 'Slat_Section_mm', '60 x 100')
    screen.set_attribute('BIM_Data', 'Slat_Centres_mm', 180)
    screen.set_attribute('BIM_Data', 'Material_Key', timber.name)

    trim = 0.090
    add_box(screen.entities, "#{name}_Frame_Left", x0, y, z0, trim, 0.110, height, timber, wood_tag)
    add_box(screen.entities, "#{name}_Frame_Right", x1 - trim, y, z0, trim, 0.110, height, timber, wood_tag)
    add_box(screen.entities, "#{name}_Frame_Bottom", x0, y, z0, width, 0.110, trim, timber, wood_tag)
    add_box(screen.entities, "#{name}_Frame_Top", x0, y, z1 - trim, width, 0.110, trim, timber, wood_tag)

    count = [(width / 0.18).round, 3].max
    (1...count).each do |index|
      x = x0 + width * index / count
      add_box(screen.entities, format('%s_Slat_%02d', name, index),
              x - 0.030, y - 0.010, z0 + trim, 0.060, 0.100, height - 2 * trim, timber, wood_tag)
    end
    screen
  end

  # ------------------------------------------------------------------ build
  def build!
    model = Sketchup.active_model
    FileUtils.mkdir_p(OUTPUT_DIR)
    model.start_operation('Generate Modern House Reference 02', true)
    model.entities.clear!
    # Definitions first: vertical_grain! paints faces *inside* group definitions,
    # so those definitions keep a material alive if materials are purged first.
    model.definitions.purge_unused
    model.materials.purge_unused

    units = model.options['UnitsOptions']
    units['LengthUnit'] = 4 # metres
    units['LengthFormat'] = 0
    units['LengthPrecision'] = 3
    units['SuppressUnitsDisplay'] = false

    model.set_attribute('Project_Information', 'Project_Name', 'Modern House Reference 02')
    model.set_attribute('Project_Information', 'Model_Type', 'Conceptual exterior massing model')
    model.set_attribute('Project_Information', 'Parti',
                        'Board-formed concrete tower with full-height glazed slot; white tile upper volume cantilevered 2.0 m over a glazed ground floor; cedar screen to the west bedrooms.')
    model.set_attribute('Project_Information', 'Overall_Width_m', WIDTH)
    model.set_attribute('Project_Information', 'Overall_Depth_m', DEPTH)
    model.set_attribute('Project_Information', 'Overall_Height_m', TOP + 0.05)
    model.set_attribute('Project_Information', 'Ground_FFL_m', FFL)
    model.set_attribute('Project_Information', 'Upper_Level_m', L2)
    model.set_attribute('Project_Information', 'Cantilever_m', CANTILEVER)
    model.set_attribute('Project_Information', 'Units', 'metre')
    model.set_attribute('Project_Information', 'Texture_Library', TEXTURE_DIR)
    model.set_attribute('Project_Information', 'Front_Elevation_Faces', '-Y (south)')
    model.set_attribute('Project_Information', 'Authoring_Note',
                        'Side and rear conditions are rationalized conceptual geometry, not survey data.')

    # Material names are the plain Chinese finish names so they are readable in
    # the Materials browser and in the entity info panel. The original coded key
    # is kept in the attribute dictionary as Legacy_Key for traceability.
    mats = {
      tile: ensure_material(model, '白色磁磚',
                            [242, 240, 236], 1.0,
                            { 'Category' => 'Exterior wall finish', 'Colour' => 'White',
                              'Finish' => 'Matte glazed ceramic', 'Module' => '300 x 300 mm, 3 mm joint',
                              'Legacy_Key' => 'MAT-01_Ceramic-Tile-Cladding_White_Matte_300x300mm' },
                            'wall_tile_white.png', 0.600),
      concrete: ensure_material(model, '清水混凝土',
                                [152, 152, 150], 1.0,
                                { 'Category' => 'Structural mass and site walls', 'Colour' => 'Light gray',
                                  'Finish' => 'Board-formed, tie holes expressed',
                                  'Legacy_Key' => 'MAT-02_Architectural-Concrete_Light-Gray_Board-Formed' },
                                'wall_concrete_grey.png', 1.200),
      cedar: ensure_material(model, '木飾板',
                             [150, 105, 65], 1.0,
                             { 'Category' => 'Timber screen, entry wall and door', 'Species' => 'Western red cedar',
                               'Finish' => 'Exterior oiled', 'Module' => '200 mm vertical boards',
                               'Legacy_Key' => 'MAT-03_Cedar-Timber-Cladding_Warm-Brown_Vertical-200mm' },
                             'wall_wood_cedar.png', 0.800),
      metal: ensure_material(model, '金屬屋面',
                             [80, 84, 92], 1.0,
                             { 'Category' => 'Roof covering and copings', 'Colour' => 'Dark gray',
                               'Finish' => 'Matte standing seam, 225 mm bays',
                               'Legacy_Key' => 'MAT-04_Standing-Seam-Metal-Roof_Dark-Gray_Matte' },
                             'roof_metal_darkgrey.png', 0.900),
      oak: ensure_material(model, '橡木地板',
                           [178, 132, 86], 1.0,
                           { 'Category' => 'Interior floor visible through glazing', 'Species' => 'European oak',
                             'Finish' => 'Natural oil', 'Module' => '200 mm staggered planks',
                             'Legacy_Key' => 'MAT-05_Oak-Timber-Flooring_Natural_200mm-Plank' },
                           'floor_wood_oak.png', 1.200),
      lawn: ensure_material(model, '草地',
                            [140, 172, 104], 1.0,
                            { 'Category' => 'Site ground cover', 'Colour' => 'Deep green', 'Finish' => 'Mown turf',
                              'Legacy_Key' => 'MAT-06_Lawn-Turf_Deep-Green_Mown' },
                            'site_grass_green.png', 2.000),
      glass: ensure_material(model, '清玻璃',
                             [96, 128, 142], 0.38,
                             { 'Category' => 'Exterior glazing', 'Type' => 'Low-E double glazed unit',
                               'Tint' => 'Blue-gray', 'Thickness_mm' => 28,
                               'Legacy_Key' => 'MAT-07_Low-E-Insulated-Glass_Blue-Gray_Clear' }),
      smoked: ensure_material(model, '煙燻玻璃',
                              [70, 60, 54], 0.55,
                              { 'Category' => 'Screen backing glazing', 'Tint' => 'Dark bronze',
                                'Legacy_Key' => 'MAT-08_Smoked-Glass_Dark-Bronze_Translucent' }),
      frame: ensure_material(model, '深色鋁框',
                             [52, 48, 45], 1.0,
                             { 'Category' => 'Window and door framing', 'Finish' => 'Dark bronze anodized',
                               'Legacy_Key' => 'MAT-09_Aluminium-Frame_Dark-Bronze_Anodized-Matte' }),
      shadow: ensure_material(model, '室內陰影',
                              [34, 36, 38], 1.0,
                              { 'Category' => 'Interior visual backing', 'Finish' => 'Matte',
                                'Legacy_Key' => 'MAT-10_Interior-Shadow_Dark-Charcoal_Matte' }),
      water: ensure_material(model, '水池',
                             [46, 62, 68], 0.78,
                             { 'Category' => 'Reflecting pool', 'Finish' => 'Still water over dark slate',
                               'Legacy_Key' => 'MAT-11_Water-Feature_Dark-Slate_Still' }),
      planting: ensure_material(model, '植栽',
                                [64, 92, 58], 1.0,
                                { 'Category' => 'Concept landscape planting', 'Planting' => 'Mixed shrub and tree',
                                  'Legacy_Key' => 'MAT-12_Landscape-Planting_Deep-Green_Mixed-Shrub' })
    }

    tags = {
      site: ensure_tag(model, '00_Site-and-Paving'),
      mass: ensure_tag(model, '01_Building-Massing'),
      tile: ensure_tag(model, '02_White-Tile-Cladding'),
      concrete: ensure_tag(model, '03_Concrete-Elements'),
      glass: ensure_tag(model, '04_Glazing'),
      wood: ensure_tag(model, '05_Timber-Screen-and-Door'),
      metal: ensure_tag(model, '06_Metal-Framing'),
      landscape: ensure_tag(model, '07_Landscape'),
      dims: ensure_tag(model, '08_Reference-Dimensions', false)
    }

    e = model.entities

    # ---- 00 site and paving ------------------------------------------------
    add_box(e, 'Site_Lawn', -12.0, -18.0, -0.30, 36.0, 34.0, 0.30, mats[:lawn], tags[:site],
            'Element_Type' => 'site ground')
    add_box(e, 'Front_Terrace_Paving', -1.5, -7.0, 0.0, 17.0, 7.0, 0.12, mats[:concrete], tags[:site],
            'Element_Type' => 'paving')
    3.times do |i|
      add_box(e, format('Entry_Step_%02d', i + 1), 4.0, -1.35 + i * 0.45, 0.12,
              3.4, 1.35 - i * 0.45, 0.11 * (i + 1), mats[:concrete], tags[:site],
              'Element_Type' => 'step', 'Riser_mm' => 110)
    end
    add_box(e, 'Pool_Rim_North', -1.20, -1.65, 0.12, 4.80, 0.25, 0.24, mats[:concrete], tags[:site])
    add_box(e, 'Pool_Rim_South', -1.20, -5.60, 0.12, 4.80, 0.25, 0.24, mats[:concrete], tags[:site])
    add_box(e, 'Pool_Rim_West', -1.20, -5.35, 0.12, 0.25, 3.70, 0.24, mats[:concrete], tags[:site])
    add_box(e, 'Pool_Rim_East', 3.35, -5.35, 0.12, 0.25, 3.70, 0.24, mats[:concrete], tags[:site])
    add_box(e, 'Pool_Water_Surface', -0.95, -5.35, 0.12, 4.30, 3.70, 0.18, mats[:water], tags[:site],
            'Element_Type' => 'water feature', 'Surface_Area_m2' => 15.91)

    # ---- 01/03 concrete tower ---------------------------------------------
    add_box(e, 'Concrete_Tower_West_Pier', 0.0, 0.0, 0.0, 1.40, 10.0, TOP, mats[:concrete], tags[:concrete],
            'Element_Type' => 'primary mass')
    add_box(e, 'Concrete_Tower_East_Pier', 2.0, 0.0, 0.0, 2.20, 10.0, TOP, mats[:concrete], tags[:concrete],
            'Element_Type' => 'primary mass')
    add_box(e, 'Concrete_Tower_Base_Lintel', 1.40, 0.0, 0.0, 0.60, 10.0, 1.20, mats[:concrete], tags[:concrete])
    add_box(e, 'Concrete_Tower_Head_Lintel', 1.40, 0.0, 6.40, 0.60, 10.0, 0.65, mats[:concrete], tags[:concrete])
    add_box(e, 'Tower_Slot_Reveal', 1.40, 0.25, 1.20, 0.60, 9.75, 5.20, mats[:shadow], tags[:mass])
    add_box(e, 'Tower_Slot_Glazing', 1.40, 0.22, 1.20, 0.60, 0.03, 5.20, mats[:glass], tags[:glass],
            'Element_Type' => 'feature glazing', 'Clear_Opening_m' => '0.60 x 5.20')

    # ---- ground floor ------------------------------------------------------
    add_box(e, 'Ground_Floor_Slab', 4.20, 0.0, 0.0, 9.80, 10.0, FFL, mats[:concrete], tags[:concrete],
            'Element_Type' => 'floor slab')
    add_box(e, 'Ground_Interior_Oak_Floor', 4.20, 0.02, FFL, 9.50, 9.66, 0.03, mats[:oak], tags[:mass],
            'Element_Type' => 'interior floor', 'Floor_Area_m2' => 91.8)
    add_box(e, 'Ground_East_Wall', 13.70, 0.0, FFL, 0.30, 10.0, L2 - FFL, mats[:tile], tags[:tile])
    add_box(e, 'Ground_Rear_Wall', 4.20, 9.70, FFL, 9.80, 0.30, L2 - FFL, mats[:tile], tags[:tile])
    add_box(e, 'Ground_Interior_Backdrop', 4.40, 8.60, 0.48, 9.20, 1.10, 3.20, mats[:shadow], tags[:mass])
    add_box(e, 'Ground_Ceiling_Shadow', 4.20, 0.0, 3.62, 9.50, 9.70, 0.13, mats[:shadow], tags[:mass])

    # ---- entry -------------------------------------------------------------
    entry_wall = add_box(e, 'Entry_Timber_Wall', 4.20, -0.12, FFL, 2.34, 0.12, L2 - FFL,
                         mats[:cedar], tags[:wood], 'Element_Type' => 'clad wall', 'Grain' => 'vertical')
    vertical_grain!(entry_wall, mats[:cedar], 0.800)
    # The reveal sits *behind* the leaf so it reads as a 30 mm shadow gap.
    add_box(e, 'Entry_Door_Reveal', 4.72, -0.14, FFL, 1.26, 0.02, 2.68, mats[:shadow], tags[:wood])
    entry_door = add_box(e, 'Entry_Door_Leaf', 4.75, -0.20, FFL, 1.20, 0.06, 2.65,
                         mats[:cedar], tags[:wood],
                         'Element_Type' => 'entrance door', 'Leaf_Width_m' => 1.20,
                         'Leaf_Height_m' => 2.65, 'Grain' => 'vertical')
    vertical_grain!(entry_door, mats[:cedar], 0.800)
    add_box(e, 'Entry_Door_Pull_Handle', 5.80, -0.26, 1.00, 0.05, 0.06, 0.90, mats[:frame], tags[:metal])

    # ---- ground glazing ----------------------------------------------------
    add_glazing(e, 'Ground_Living_Glazing', 6.60, 13.65, 0.0, 0.50, 3.50, 4,
                mats[:glass], mats[:frame], tags[:glass], tags[:metal])
    # Closes the strip between the glazing head and the underside of the slab.
    add_box(e, 'Ground_Front_Head_Band', 6.54, -0.05, 3.56, 7.16, 0.05, L2 - 3.56,
            mats[:tile], tags[:tile], 'Element_Type' => 'head band')

    # ---- upper volume ------------------------------------------------------
    add_box(e, 'Upper_Floor_Slab', 4.20, -CANTILEVER, L2, 9.80, 10.60, 0.30, mats[:tile], tags[:tile],
            'Element_Type' => 'cantilevered slab', 'Cantilever_m' => CANTILEVER)
    add_box(e, 'Upper_Roof_Slab', 4.20, -CANTILEVER, 6.75, 9.80, 10.60, 0.30, mats[:tile], tags[:tile])
    # East elevation is split around a punched window so the opening reads as a
    # real reveal rather than a panel laid over a solid wall.
    add_box(e, 'Upper_East_Wall_South', 13.70, -CANTILEVER, 4.05, 0.30, 3.20, 2.70, mats[:tile], tags[:tile])
    add_box(e, 'Upper_East_Wall_North', 13.70, 4.80, 4.05, 0.30, 3.80, 2.70, mats[:tile], tags[:tile])
    add_box(e, 'Upper_East_Wall_Sill', 13.70, 1.20, 4.05, 0.30, 3.60, 0.55, mats[:tile], tags[:tile])
    add_box(e, 'Upper_East_Wall_Head', 13.70, 1.20, 6.20, 0.30, 3.60, 0.55, mats[:tile], tags[:tile])
    add_glazing_east(e, 'Upper_East_Window', 1.20, 4.80, 13.97, 4.60, 6.20, 2,
                     mats[:glass], mats[:frame], tags[:glass], tags[:metal])
    add_box(e, 'Upper_West_Return', 4.20, -CANTILEVER, 4.05, 0.30, 2.00, 2.70, mats[:tile], tags[:tile])
    add_box(e, 'Upper_Rear_Wall', 4.20, 8.30, 4.05, 9.80, 0.30, 2.70, mats[:tile], tags[:tile])
    add_box(e, 'Upper_Interior_Oak_Floor', 4.50, -1.90, 4.05, 9.20, 10.20, 0.03, mats[:oak], tags[:mass])
    add_box(e, 'Upper_Interior_Backdrop', 4.50, 6.90, 4.08, 9.20, 1.40, 2.67, mats[:shadow], tags[:mass])

    # Front facade of the upper volume. The two openings are punched out of a
    # solid tile wall; without these pieces the glazing and the screen float in
    # an open frame and the volume can be seen straight through.
    # Set back 10 mm from the slab edges so the frames read proud, not co-planar.
    fw_y = -CANTILEVER + 0.01
    add_box(e, 'Upper_Front_Wall_Pier_West', 4.20, fw_y, 4.05, 0.65, 0.30, 2.70, mats[:tile], tags[:tile],
            'Element_Type' => 'facade pier')
    add_box(e, 'Upper_Front_Wall_Pier_Centre', 9.55, fw_y, 4.05, 0.30, 0.30, 2.70, mats[:tile], tags[:tile],
            'Element_Type' => 'facade pier')
    add_box(e, 'Upper_Front_Wall_Pier_East', 13.55, fw_y, 4.05, 0.15, 0.30, 2.70, mats[:tile], tags[:tile],
            'Element_Type' => 'facade pier')
    add_box(e, 'Upper_Front_Wall_Spandrel', 4.85, fw_y, 4.05, 8.70, 0.30, 0.30, mats[:tile], tags[:tile],
            'Element_Type' => 'spandrel')
    add_box(e, 'Upper_Front_Wall_Head', 4.85, fw_y, 6.55, 8.70, 0.30, 0.20, mats[:tile], tags[:tile],
            'Element_Type' => 'head beam')

    add_glazing(e, 'Upper_Living_Glazing', 4.85, 9.55, -1.95, 4.35, 6.55, 3,
                mats[:glass], mats[:frame], tags[:glass], tags[:metal])
    add_timber_screen(e, 'Upper_Bedroom_Cedar_Screen', 9.85, 13.55, -1.98, 4.35, 6.55,
                      mats[:cedar], mats[:smoked], tags[:wood], tags[:glass])

    # ---- roof --------------------------------------------------------------
    add_box(e, 'Roof_Covering_Upper_Volume', 4.20, -CANTILEVER, TOP, 9.80, 10.60, 0.05,
            mats[:metal], tags[:metal], 'Element_Type' => 'roof covering', 'Area_m2' => 103.88)
    add_box(e, 'Roof_Covering_Concrete_Tower', 0.0, 0.0, TOP, 4.20, 10.0, 0.05,
            mats[:metal], tags[:metal], 'Element_Type' => 'roof covering', 'Area_m2' => 42.0)

    # ---- 07 landscape ------------------------------------------------------
    add_box(e, 'Planter_East_Wall', 9.80, -6.60, 0.12, 5.70, 2.20, 0.50, mats[:concrete], tags[:landscape])
    add_box(e, 'Planter_East_Planting_Bed', 9.95, -6.45, 0.55, 5.40, 1.90, 0.12, mats[:planting], tags[:landscape])
    5.times do |i|
      add_cylinder(e, format('Concept_Shrub_%02d', i + 1), 10.55 + i * 1.10, -5.50, 0.62,
                   0.34, 0.40 + (i % 2) * 0.14, 16, mats[:planting], tags[:landscape])
    end
    # Three stepped tiers read as a canopy without importing a proxy component.
    [[20.20, -7.40], [-5.60, -9.60]].each_with_index do |(tx, ty), i|
      add_cylinder(e, format('Concept_Tree_%02d_Trunk', i + 1), tx, ty, 0.0, 0.13, 2.30, 12,
                   mats[:cedar], tags[:landscape])
      [[1.90, 1.42, 0.42], [2.32, 1.20, 0.42], [2.74, 0.96, 0.42],
       [3.16, 0.68, 0.42], [3.58, 0.34, 0.34]].each_with_index do |(z, r, h), tier|
        add_cylinder(e, format('Concept_Tree_%02d_Canopy_%02d', i + 1, tier + 1), tx, ty, z, r, h, 20,
                     mats[:planting], tags[:landscape])
      end
    end

    # ---- 08 reference dimensions (hidden) ---------------------------------
    dim_w = e.add_dimension_linear(point(0.0, -2.6, 0.0), point(WIDTH, -2.6, 0.0), vector(0.0, -0.9, 0.0))
    dim_w.layer = tags[:dims]
    dim_h = e.add_dimension_linear(point(WIDTH, 0.0, 0.0), point(WIDTH, 0.0, TOP), vector(0.9, 0.0, 0.0))
    dim_h.layer = tags[:dims]
    dim_d = e.add_dimension_linear(point(WIDTH, -CANTILEVER, 0.0), point(WIDTH, 10.0, 0.0), vector(0.9, 0.0, 0.0))
    dim_d.layer = tags[:dims]

    # ---- shadows -----------------------------------------------------------
    shadows = model.shadow_info
    shadows['DisplayShadows'] = true
    shadows['UseSunForAllShading'] = true
    shadows['Light'] = 72
    shadows['Dark'] = 52

    # ---- scenes ------------------------------------------------------------
    pages = model.pages
    pages.to_a.each { |page| pages.erase(page) }
    view = model.active_view

    perspective = Sketchup::Camera.new(point(25.5, -25.0, 10.5), point(6.8, 2.2, 3.20),
                                       Geom::Vector3d.new(0, 0, 1), true)
    perspective.fov = 34.0
    view.camera = perspective
    page_perspective = pages.add('01_Front_Perspective')
    page_perspective.description = 'Primary three-quarter view from the south-east approach.'

    front = Sketchup::Camera.new(point(7.0, -32.0, 3.60), point(7.0, 0.0, 3.60),
                                 Geom::Vector3d.new(0, 0, 1), false)
    front.height = m(10.5)
    view.camera = front
    page_front = pages.add('02_Front_Orthographic')
    page_front.description = 'Dimensionally undistorted front elevation.'

    aerial = Sketchup::Camera.new(point(28.0, -22.0, 24.0), point(7.0, 3.5, 2.0),
                                  Geom::Vector3d.new(0, 0, 1), true)
    aerial.fov = 40.0
    view.camera = aerial
    page_aerial = pages.add('03_Site_Aerial')
    page_aerial.description = 'Aerial showing the site, terrace and reflecting pool.'

    pages.selected_page = page_perspective
    model.definitions.purge_unused
    model.materials.purge_unused
    # Template leftovers (e.g. the default "材料") survive purge_unused; drop
    # anything that this script did not author so the browser lists only finishes.
    model.materials.to_a.each do |leftover|
      next if leftover.attribute_dictionary('Material_Specification')
      begin
        model.materials.remove(leftover)
      rescue StandardError
        nil
      end
    end
    model.commit_operation
    model.save(SKP_PATH)

    begin
      # selected_page= does not apply its camera synchronously, so restate it.
      view.camera = perspective
      view.refresh
      view.write_image(filename: PNG_PATH, width: 1600, height: 1000,
                       antialias: true, transparent: false)
    rescue StandardError => preview_error
      File.open(LOG_PATH, 'a:utf-8') { |f| f.puts("Preview warning: #{preview_error.message}") }
    end

    groups = model.entities.grep(Sketchup::Group).length
    summary = "BUILD_OK groups=#{groups} materials=#{model.materials.length} " \
              "tags=#{model.layers.length} scenes=#{pages.count} skp=#{SKP_PATH}"
    File.open(LOG_PATH, 'a:utf-8') do |f|
      f.puts("#{summary} at #{Time.now}")
      f.puts("Overall: #{WIDTH} m W x #{DEPTH} m D x #{(TOP + 0.05).round(2)} m H")
    end
    summary
  rescue StandardError => error
    begin
      Sketchup.active_model.abort_operation
    rescue StandardError
      nil
    end
    FileUtils.mkdir_p(OUTPUT_DIR)
    File.open(LOG_PATH, 'a:utf-8') do |f|
      f.puts("BUILD_FAILED #{Time.now}")
      f.puts("#{error.class}: #{error.message}")
      f.puts(error.backtrace.first(12).join("\n"))
    end
    "BUILD_FAILED #{error.class}: #{error.message} @ #{error.backtrace.first}"
  end
end

$MODERN_HOUSE_02 = ModernHouse02.build!
