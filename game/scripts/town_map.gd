extends TileMapLayer

## Visual ground only. Agent positions stay on the server.
## POI nodes are the coordinate source; world.gd checks them against
## backend/app/simulation/poi.py. Paths are the straight segments the
## v0.1 schedules actually walk (fake_agent.py moves in a straight line).

const TILE := 16
const MAP_SIZE := Vector2i(80, 45)
const BUILDING_TILES := 4
## NPC ColorRect is 20×20 and axis-aligned, so a corner sits ~14px off a
## diagonal path. Tiles that come within this distance of the centerline
## are path, which keeps that square on road or building tiles.
const NPC_COVER := 18.0
const PATH_SAMPLE := 4.0

const A_GRASS := Vector2i(0, 0)
const A_GRASS_B := Vector2i(1, 0)
const A_FLOWER := Vector2i(2, 0)
const A_SHADOW := Vector2i(3, 0)
const A_ROAD := Vector2i(4, 0)
const A_TREE := Vector2i(5, 0)
const A_HOME_CAP := Vector2i(6, 0)
const A_HOME_EAVE := Vector2i(7, 0)
const A_HOME_WALL := Vector2i(8, 0)
const A_HOME_DOOR := Vector2i(9, 0)
const A_CAFE_CAP := Vector2i(10, 0)
const A_CAFE_EAVE := Vector2i(11, 0)
const A_CAFE_WALL := Vector2i(12, 0)
const A_CAFE_DOOR := Vector2i(13, 0)
const A_OFFICE_CAP := Vector2i(14, 0)
const A_OFFICE_EAVE := Vector2i(15, 0)
const A_OFFICE_WALL := Vector2i(16, 0)
const A_OFFICE_DOOR := Vector2i(17, 0)
const A_PARK_CAP := Vector2i(18, 0)
const A_PARK_EAVE := Vector2i(19, 0)
const A_PARK_POST_L := Vector2i(20, 0)
const A_PARK_POST_R := Vector2i(21, 0)
const A_PARK_FLOOR := Vector2i(22, 0)
const A_PARK_GATE := Vector2i(23, 0)
const ATLAS_COUNT := 24

## Node-name pairs. Home–cafe, cafe–office, office–park, park–home.
const WALKED_EDGES: Array = [
	["Home", "Cafe"],
	["Cafe", "Office"],
	["Office", "Park"],
	["Park", "Home"],
]

var _source_id := 0


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	_rebuild()


func _rebuild() -> void:
	var image := _build_atlas()
	var texture := ImageTexture.create_from_image(image)
	var atlas := TileSetAtlasSource.new()
	atlas.texture = texture
	atlas.texture_region_size = Vector2i(TILE, TILE)
	for i in ATLAS_COUNT:
		atlas.create_tile(Vector2i(i, 0))
	var tileset := TileSet.new()
	tileset.tile_size = Vector2i(TILE, TILE)
	tileset.uv_clipping = true
	_source_id = tileset.add_source(atlas)
	tile_set = tileset
	_paint()


func _paint() -> void:
	_paint_grass()
	var pois := _read_pois()
	if pois.is_empty():
		return
	for edge in WALKED_EDGES:
		_paint_road(pois[edge[0]], pois[edge[1]])
	_paint_house(pois["Home"], A_HOME_CAP, A_HOME_EAVE, A_HOME_WALL, A_HOME_DOOR, "Home")
	_paint_house(pois["Cafe"], A_CAFE_CAP, A_CAFE_EAVE, A_CAFE_WALL, A_CAFE_DOOR, "Cafe")
	_paint_house(pois["Office"], A_OFFICE_CAP, A_OFFICE_EAVE, A_OFFICE_WALL, A_OFFICE_DOOR, "Office")
	_paint_pavilion(pois["Park"])
	_paint_trees(pois["Park"])
	for edge in WALKED_EDGES:
		_warn_if_npc_would_leave_path(pois[edge[0]], pois[edge[1]])


func _read_pois() -> Dictionary:
	var pois := {}
	for node_name in ["Home", "Cafe", "Office", "Park"]:
		var node := get_node_or_null("../POIs/%s" % node_name) as Node2D
		if node == null:
			push_error("Town map missing POIs/%s" % node_name)
			return {}
		pois[node_name] = node.position
	return pois


func _paint_grass() -> void:
	for y in MAP_SIZE.y:
		for x in MAP_SIZE.x:
			set_cell(Vector2i(x, y), _source_id, _grass_atlas(x, y))


func _grass_atlas(x: int, y: int) -> Vector2i:
	var n := (x * 13 + y * 29) % 96
	if n == 0:
		return A_FLOWER
	if (x * 13 + y * 17) % 7 == 0:
		return A_GRASS_B
	return A_GRASS


func _paint_road(a: Vector2, b: Vector2) -> void:
	var length := a.distance_to(b)
	var steps := maxi(1, int(ceil(length / PATH_SAMPLE)))
	for i in steps + 1:
		var point: Vector2 = a.lerp(b, float(i) / float(steps))
		_stamp_path(point)


func _stamp_path(point: Vector2) -> void:
	var c0 := maxi(0, int(floor((point.x - NPC_COVER) / float(TILE))))
	var c1 := mini(MAP_SIZE.x - 1, int(floor((point.x + NPC_COVER) / float(TILE))))
	var r0 := maxi(0, int(floor((point.y - NPC_COVER) / float(TILE))))
	var r1 := mini(MAP_SIZE.y - 1, int(floor((point.y + NPC_COVER) / float(TILE))))
	for r in range(r0, r1 + 1):
		for c in range(c0, c1 + 1):
			if _dist_to_cell(point, c, r) <= NPC_COVER:
				set_cell(Vector2i(c, r), _source_id, A_ROAD)


func _dist_to_cell(point: Vector2, c: int, r: int) -> float:
	var min_x := float(c * TILE)
	var min_y := float(r * TILE)
	var closest := Vector2(
		clampf(point.x, min_x, min_x + float(TILE)),
		clampf(point.y, min_y, min_y + float(TILE)),
	)
	return point.distance_to(closest)


func _paint_house(
	center: Vector2,
	cap: Vector2i,
	eave: Vector2i,
	wall: Vector2i,
	door: Vector2i,
	label: String,
) -> void:
	var origin := _building_origin(center)
	_assert_covers(origin, center, label)
	for ly in BUILDING_TILES:
		for lx in BUILDING_TILES:
			var atlas := wall
			if ly == 0:
				atlas = cap
			elif ly == 1:
				atlas = eave
			elif ly == BUILDING_TILES - 1 and (lx == 1 or lx == 2):
				atlas = door
			_set_tile(origin + Vector2i(lx, ly), atlas)
	_paint_shadow(origin)


func _paint_pavilion(center: Vector2) -> void:
	var origin := _building_origin(center)
	_assert_covers(origin, center, "Park")
	for ly in BUILDING_TILES:
		for lx in BUILDING_TILES:
			var atlas := A_PARK_FLOOR
			if ly == 0:
				atlas = A_PARK_CAP
			elif ly == 1:
				atlas = A_PARK_EAVE
			elif lx == 0:
				atlas = A_PARK_POST_L
			elif lx == BUILDING_TILES - 1:
				atlas = A_PARK_POST_R
			elif ly == BUILDING_TILES - 1 and (lx == 1 or lx == 2):
				atlas = A_PARK_GATE
			_set_tile(origin + Vector2i(lx, ly), atlas)
	_paint_shadow(origin)


func _building_origin(center: Vector2) -> Vector2i:
	var half := int(BUILDING_TILES / 2)
	return Vector2i(
		int(round(center.x / float(TILE))) - half,
		int(round(center.y / float(TILE))) - half,
	)


func _assert_covers(origin: Vector2i, center: Vector2, label: String) -> void:
	var rect := Rect2(
		origin.x * TILE,
		origin.y * TILE,
		BUILDING_TILES * TILE,
		BUILDING_TILES * TILE,
	)
	if not rect.has_point(center):
		push_error("%s building %s does not cover POI %s" % [label, rect, center])


func _paint_shadow(origin: Vector2i) -> void:
	var row := origin.y + BUILDING_TILES
	for lx in BUILDING_TILES:
		var cell := Vector2i(origin.x + lx, row)
		if _in_map(cell) and _is_open_ground(cell):
			set_cell(cell, _source_id, A_SHADOW)


func _paint_trees(park: Vector2) -> void:
	var origin := _building_origin(park)
	for offset in _park_tree_offsets():
		_try_tree(origin + offset)
	for y in range(1, MAP_SIZE.y - 1):
		for x in range(1, MAP_SIZE.x - 1):
			if (x * 19 + y * 37) % 67 != 0:
				continue
			_try_tree(Vector2i(x, y))


func _park_tree_offsets() -> Array[Vector2i]:
	return [
		Vector2i(-3, 0),
		Vector2i(-3, 2),
		Vector2i(-2, 4),
		Vector2i(1, 5),
		Vector2i(3, 5),
		Vector2i(5, 3),
		Vector2i(5, 1),
		Vector2i(4, -2),
		Vector2i(6, 0),
		Vector2i(-4, 3),
		Vector2i(2, 6),
		Vector2i(-1, 6),
	]


func _try_tree(cell: Vector2i) -> void:
	if not _in_map(cell) or not _is_open_ground(cell):
		return
	for oy in range(-1, 2):
		for ox in range(-1, 2):
			var neighbor := cell + Vector2i(ox, oy)
			if not _in_map(neighbor) or not _is_open_ground(neighbor):
				return
	set_cell(cell, _source_id, A_TREE)


func _warn_if_npc_would_leave_path(a: Vector2, b: Vector2) -> void:
	var length := a.distance_to(b)
	if length < 1.0:
		return
	var steps := int(ceil(length / 4.0))
	var offsets: Array[Vector2] = [
		Vector2(10, 10),
		Vector2(10, -10),
		Vector2(-10, 10),
		Vector2(-10, -10),
		Vector2(10, 0),
		Vector2(-10, 0),
		Vector2(0, 10),
		Vector2(0, -10),
	]
	for i in steps + 1:
		var point: Vector2 = a.lerp(b, float(i) / float(steps))
		for offset in offsets:
			if not _tile_supports_npc(point + offset):
				push_error("NPC body leaves the path at %s on %s -> %s" % [point + offset, a, b])
				return


func _tile_supports_npc(point: Vector2) -> bool:
	if point.x < 0.0 or point.y < 0.0:
		return false
	var cell := Vector2i(int(floor(point.x / float(TILE))), int(floor(point.y / float(TILE))))
	if not _in_map(cell):
		return false
	if _is_open_ground(cell):
		return false
	var atlas := get_cell_atlas_coords(cell)
	return atlas != A_TREE and atlas != A_SHADOW


func _is_open_ground(cell: Vector2i) -> bool:
	var atlas := get_cell_atlas_coords(cell)
	return atlas == A_GRASS or atlas == A_GRASS_B or atlas == A_FLOWER


func _in_map(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < MAP_SIZE.x and cell.y < MAP_SIZE.y


func _set_tile(cell: Vector2i, atlas: Vector2i) -> void:
	if _in_map(cell):
		set_cell(cell, _source_id, atlas)


func _build_atlas() -> Image:
	var image := Image.create(ATLAS_COUNT * TILE, TILE, false, Image.FORMAT_RGBA8)
	image.fill(Color(0, 0, 0, 0))
	var grass := Color8(112, 158, 78)
	var grass_dark := Color8(78, 122, 56)
	var grass_light := Color8(150, 186, 104)
	_draw_grass(image, A_GRASS.x, grass, grass_dark, grass_light, 0)
	_draw_grass(image, A_GRASS_B.x, Color8(102, 148, 72), grass_dark, grass_light, 3)
	_draw_flower(image, grass, grass_dark, grass_light)
	_draw_grass(image, A_SHADOW.x, Color8(72, 112, 54), Color8(56, 90, 42), Color8(96, 132, 70), 1)
	_draw_road(image)
	_draw_tree(image, grass, grass_dark, grass_light)
	_draw_flat_roof(image, A_HOME_CAP.x, Color8(176, 78, 62), Color8(214, 118, 96), Color8(120, 48, 40), false)
	_draw_flat_roof(image, A_HOME_EAVE.x, Color8(176, 78, 62), Color8(214, 118, 96), Color8(120, 48, 40), true)
	_draw_house_wall(image, A_HOME_WALL.x, Color8(240, 224, 196), Color8(120, 84, 60), Color8(142, 188, 206))
	_draw_door(image, A_HOME_DOOR.x, Color8(240, 224, 196), Color8(92, 56, 38), Color8(230, 200, 120))
	_draw_awning(image, A_CAFE_CAP.x, Color8(214, 86, 70), Color8(246, 220, 186), Color8(120, 48, 40), false)
	_draw_awning(image, A_CAFE_EAVE.x, Color8(214, 86, 70), Color8(246, 220, 186), Color8(120, 48, 40), true)
	_draw_shop_wall(image, A_CAFE_WALL.x, Color8(255, 244, 230), Color8(140, 72, 52), Color8(255, 214, 140))
	_draw_door(image, A_CAFE_DOOR.x, Color8(255, 244, 230), Color8(110, 62, 46), Color8(255, 220, 140))
	_draw_flat_roof(image, A_OFFICE_CAP.x, Color8(62, 86, 118), Color8(110, 140, 170), Color8(40, 56, 78), false)
	_draw_flat_roof(image, A_OFFICE_EAVE.x, Color8(62, 86, 118), Color8(110, 140, 170), Color8(40, 56, 78), true)
	_draw_office_wall(image, A_OFFICE_WALL.x, Color8(214, 224, 232), Color8(62, 86, 112), Color8(126, 180, 208))
	_draw_door(image, A_OFFICE_DOOR.x, Color8(214, 224, 232), Color8(46, 62, 88), Color8(180, 210, 220))
	_draw_flat_roof(image, A_PARK_CAP.x, Color8(46, 128, 86), Color8(96, 176, 122), Color8(90, 60, 36), false)
	_draw_flat_roof(image, A_PARK_EAVE.x, Color8(46, 128, 86), Color8(96, 176, 122), Color8(120, 78, 46), true)
	_draw_post(image, A_PARK_POST_L.x, true)
	_draw_post(image, A_PARK_POST_R.x, false)
	_draw_floor(image)
	_draw_gate(image)
	return image


func _draw_grass(img: Image, index: int, base: Color, dark: Color, light: Color, phase: int) -> void:
	_fill_tile(img, index, base)
	var blades: Array[Vector2i] = [
		Vector2i(2, 4),
		Vector2i(3, 3),
		Vector2i(3, 4),
		Vector2i(11, 9),
		Vector2i(12, 8),
		Vector2i(12, 9),
		Vector2i(6, 13),
		Vector2i(7, 12),
	]
	for i in blades.size():
		var blade: Vector2i = blades[i]
		var color := dark if i % 2 == 0 else light
		_px(img, index, (blade.x + phase) % TILE, (blade.y + phase * 2) % TILE, color)


func _draw_flower(img: Image, base: Color, dark: Color, light: Color) -> void:
	_draw_grass(img, A_FLOWER.x, base, dark, light, 2)
	_rect(img, A_FLOWER.x, 8, 9, 1, 5, Color8(60, 122, 48))
	_disc(img, A_FLOWER.x, 8, 7, 2, Color8(244, 214, 86))
	_px(img, A_FLOWER.x, 8, 7, Color8(232, 120, 64))


func _draw_road(img: Image) -> void:
	var index := A_ROAD.x
	_fill_tile(img, index, Color8(196, 176, 142))
	_rect(img, index, 2, 3, 3, 2, Color8(210, 194, 162))
	_rect(img, index, 9, 8, 4, 2, Color8(176, 156, 124))
	_px(img, index, 5, 12, Color8(176, 156, 124))
	_px(img, index, 12, 4, Color8(214, 198, 168))


func _draw_tree(img: Image, base: Color, dark: Color, light: Color) -> void:
	var index := A_TREE.x
	_draw_grass(img, index, base, dark, light, 1)
	_disc(img, index, 8, 6, 6, Color8(28, 78, 36))
	_disc(img, index, 8, 6, 5, Color8(46, 122, 58))
	_disc(img, index, 6, 4, 2, Color8(110, 170, 90))
	_rect(img, index, 7, 10, 2, 6, Color8(118, 78, 42))


func _draw_flat_roof(img: Image, index: int, main: Color, highlight: Color, eave: Color, draw_eave: bool) -> void:
	_fill_tile(img, index, main)
	if draw_eave:
		_rect(img, index, 0, TILE - 3, TILE, 3, eave)
	else:
		_rect(img, index, 0, 0, TILE, 2, highlight)


func _draw_awning(img: Image, index: int, a: Color, b: Color, eave: Color, draw_eave: bool) -> void:
	for y in TILE:
		var color := b if (y % 4) < 2 else a
		_rect(img, index, 0, y, TILE, 1, color)
	if draw_eave:
		_rect(img, index, 0, TILE - 3, TILE, 3, eave)


func _draw_house_wall(img: Image, index: int, wall: Color, frame: Color, glass: Color) -> void:
	_fill_tile(img, index, wall)
	_window(img, index, 4, 4, 8, 7, frame, glass)


func _draw_shop_wall(img: Image, index: int, wall: Color, frame: Color, glass: Color) -> void:
	_fill_tile(img, index, wall)
	_window(img, index, 2, 4, 12, 8, frame, glass)


func _draw_office_wall(img: Image, index: int, wall: Color, frame: Color, glass: Color) -> void:
	_fill_tile(img, index, wall)
	_window(img, index, 1, 3, 6, 8, frame, glass)
	_window(img, index, 9, 3, 6, 8, frame, glass)


func _window(img: Image, index: int, x: int, y: int, w: int, h: int, frame: Color, glass: Color) -> void:
	_rect(img, index, x, y, w, h, frame)
	_rect(img, index, x + 1, y + 1, w - 2, h - 2, glass)
	_px(img, index, x + 1, y + 1, Color(glass.r, glass.g, glass.b).lightened(0.35))


func _draw_door(img: Image, index: int, wall: Color, door: Color, knob: Color) -> void:
	_fill_tile(img, index, wall)
	_rect(img, index, 3, 1, 10, 15, door)
	_rect(img, index, 4, 2, 8, 4, door.lightened(0.12))
	_px(img, index, 11, 9, knob)


func _draw_post(img: Image, index: int, left: bool) -> void:
	_fill_tile(img, index, Color8(214, 198, 150))
	var x := 0 if left else 11
	_rect(img, index, x, 0, 5, TILE, Color8(120, 78, 46))


func _draw_floor(img: Image) -> void:
	var index := A_PARK_FLOOR.x
	_fill_tile(img, index, Color8(214, 198, 150))
	_px(img, index, 4, 6, Color8(190, 174, 126))
	_px(img, index, 11, 11, Color8(190, 174, 126))


func _draw_gate(img: Image) -> void:
	var index := A_PARK_GATE.x
	_fill_tile(img, index, Color8(214, 198, 150))
	_rect(img, index, 1, 0, 14, 3, Color8(120, 78, 46))
	_rect(img, index, 3, 3, 10, 13, Color8(64, 96, 58))


func _fill_tile(img: Image, index: int, color: Color) -> void:
	_rect(img, index, 0, 0, TILE, TILE, color)


func _rect(img: Image, index: int, x: int, y: int, w: int, h: int, color: Color) -> void:
	for yy in h:
		for xx in w:
			_px(img, index, x + xx, y + yy, color)


func _disc(img: Image, index: int, cx: int, cy: int, radius: int, color: Color) -> void:
	var r2 := radius * radius
	for y in range(cy - radius, cy + radius + 1):
		for x in range(cx - radius, cx + radius + 1):
			var dx := x - cx
			var dy := y - cy
			if dx * dx + dy * dy <= r2:
				_px(img, index, x, y, color)


func _px(img: Image, index: int, x: int, y: int, color: Color) -> void:
	if x < 0 or y < 0 or x >= TILE or y >= TILE:
		return
	img.set_pixel(index * TILE + x, y, color)
