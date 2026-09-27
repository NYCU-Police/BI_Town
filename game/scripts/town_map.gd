extends TileMapLayer

## Visual only. Place ids and coordinates live in world.gd and must match
## backend/app/simulation/poi.py. Tiles are Kenney RPG Urban Pack, 16×16
## with 1px spacing. The pack has a rendered sample, not a tile map, so this
## layout follows that sample: pavement for the town, grass only in the park.

const TILE := 16
const MAP_W := 36
const MAP_H := 28

const GRASS := Vector2i(1, 1)
const PAVEMENT := Vector2i(9, 4)
const ROAD := Vector2i(9, 1)
const WALK := Vector2i(1, 4)
const TREE := Vector2i(21, 10)
const BENCH := Vector2i(1, 10)
const LAMP := Vector2i(0, 6)
const HEDGE := Vector2i(5, 12)
const HEDGE_END := Vector2i(6, 12)
const PLANTER := Vector2i(7, 12)
const WINDOW := Vector2i(11, 10)
const DOOR_HOME := Vector2i(13, 11)
const DOOR_CAFE := Vector2i(14, 10)
const DOOR_GLASS := Vector2i(15, 10)
const AWNING := Vector2i(6, 8)
const GLASS := Vector2i(9, 14)
const SIGN := Vector2i(6, 6)

var _source_id := 0
var _objects: TileMapLayer
var _ground: Dictionary = {}
var _blocked: Dictionary = {}


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	_objects = get_node_or_null("../Objects") as TileMapLayer
	if _objects != null:
		_objects.texture_filter = TEXTURE_FILTER_NEAREST
		_objects.y_sort_enabled = true
	_rebuild()


func _rebuild() -> void:
	var texture: Texture2D = load("res://assets/town/tilemap.png")
	var atlas := TileSetAtlasSource.new()
	atlas.texture = texture
	atlas.texture_region_size = Vector2i(TILE, TILE)
	atlas.separation = Vector2i(1, 1)
	var used: Array[Vector2i] = [
		GRASS, PAVEMENT, ROAD, WALK, TREE, BENCH, LAMP,
		HEDGE, HEDGE_END, PLANTER, WINDOW, DOOR_HOME, DOOR_CAFE, DOOR_GLASS,
		AWNING, GLASS, SIGN,
		Vector2i(16, 0), Vector2i(17, 0), Vector2i(20, 0),
		Vector2i(16, 2), Vector2i(17, 2), Vector2i(20, 2),
		Vector2i(16, 4), Vector2i(17, 4), Vector2i(20, 4),
		Vector2i(16, 6), Vector2i(17, 6), Vector2i(20, 6),
		Vector2i(12, 0), Vector2i(13, 0), Vector2i(15, 0),
		Vector2i(12, 1), Vector2i(13, 1), Vector2i(15, 1),
	]
	for coord in used:
		atlas.create_tile(coord)
	var tileset := TileSet.new()
	tileset.tile_size = Vector2i(TILE, TILE)
	tileset.uv_clipping = true
	_source_id = tileset.add_source(atlas)
	tile_set = tileset
	clear()
	if _objects != null:
		_objects.tile_set = tileset
		_objects.clear()
	_ground.clear()
	_blocked.clear()
	_paint_base()
	_paint_roads()
	_paint_park()
	_paint_plaza()
	_paint_buildings()
	_paint_props()
	for cell in _ground:
		set_cell(cell, _source_id, _ground[cell])


func _paint_base() -> void:
	for y in MAP_H:
		for x in MAP_W:
			_ground[Vector2i(x, y)] = PAVEMENT


func _fill_rect(origin: Vector2i, size: Vector2i, tile: Vector2i) -> void:
	for y in size.y:
		for x in size.x:
			_ground[origin + Vector2i(x, y)] = tile


func _paint_roads() -> void:
	_fill_rect(Vector2i(0, 5), Vector2i(MAP_W, 1), WALK)
	_fill_rect(Vector2i(0, 6), Vector2i(MAP_W, 2), ROAD)
	_fill_rect(Vector2i(0, 8), Vector2i(MAP_W, 1), WALK)
	# Door columns stay on the street so a straight walk does not enter a house.
	for column in [3, 10, 17, 24, 31]:
		for y in [6, 7]:
			_ground[Vector2i(column, y)] = ROAD
	# Grey footpath from the street, through the plaza, into the park.
	for y in range(9, MAP_H):
		_ground[Vector2i(24, y)] = ROAD


func _paint_park() -> void:
	for y in range(16, MAP_H):
		for x in range(1, MAP_W - 1):
			if x == 24:
				continue
			_ground[Vector2i(x, y)] = GRASS


func _paint_plaza() -> void:
	for y in range(9, 16):
		for x in range(15, 35):
			if x == 24:
				continue
			_ground[Vector2i(x, y)] = WALK


func _row(left: Vector2i, mid: Vector2i, right: Vector2i, width: int) -> Array:
	var cells: Array = []
	for x in width:
		if x == 0:
			cells.append(left)
		elif x == width - 1:
			cells.append(right)
		else:
			cells.append(mid)
	return cells


func _paint_buildings() -> void:
	var red_roof := _row(Vector2i(16, 0), Vector2i(17, 0), Vector2i(20, 0), 5)
	var red_wall := _row(Vector2i(16, 2), Vector2i(17, 2), Vector2i(20, 2), 5)
	var orange_roof := _row(Vector2i(16, 4), Vector2i(17, 4), Vector2i(20, 4), 5)
	var orange_wall := _row(Vector2i(16, 6), Vector2i(17, 6), Vector2i(20, 6), 5)
	var grey_roof := _row(Vector2i(12, 0), Vector2i(13, 0), Vector2i(15, 0), 5)
	var grey_wall := _row(Vector2i(12, 1), Vector2i(13, 1), Vector2i(15, 1), 5)

	_house(Vector2i(1, 1), red_roof, red_wall, DOOR_HOME, false)
	_house(Vector2i(8, 1), orange_roof, orange_wall, DOOR_HOME, false)
	_house(Vector2i(15, 1), grey_roof, grey_wall, DOOR_HOME, false)
	_house(Vector2i(22, 1), orange_roof, orange_wall, DOOR_CAFE, true)
	_house(Vector2i(29, 1), red_roof, red_wall, DOOR_GLASS, true)
	# South doors face the street, so the roof is the last row.
	_house_south(Vector2i(1, 9), grey_roof, grey_wall, DOOR_GLASS)
	_house_south(Vector2i(8, 9), orange_roof, orange_wall, DOOR_CAFE)


func _house(
	origin: Vector2i,
	roof: Array,
	wall: Array,
	door: Vector2i,
	awning: bool,
) -> void:
	var windows := wall.duplicate()
	windows[1] = WINDOW
	windows[3] = WINDOW
	var entrance := wall.duplicate()
	entrance[2] = door
	if door == DOOR_GLASS:
		entrance[1] = GLASS
		entrance[3] = GLASS
	_stamp(origin, [roof, wall, windows, entrance])
	if awning:
		_prop(origin + Vector2i(2, 2), AWNING)


func _house_south(
	origin: Vector2i,
	roof: Array,
	wall: Array,
	door: Vector2i,
) -> void:
	var windows := wall.duplicate()
	windows[1] = WINDOW
	windows[3] = WINDOW
	var entrance := wall.duplicate()
	entrance[2] = door
	_stamp(origin, [entrance, windows, wall, roof])


func _stamp(origin: Vector2i, rows: Array) -> void:
	for y in rows.size():
		var row: Array = rows[y]
		for x in row.size():
			var cell := origin + Vector2i(x, y)
			_prop(cell, row[x])
			_blocked[cell] = true


func _prop(cell: Vector2i, tile: Vector2i) -> void:
	if _objects == null:
		return
	_objects.set_cell(cell, _source_id, tile)


func _paint_props() -> void:
	for lamp_x in [6, 13, 20, 27, 33]:
		_place(Vector2i(lamp_x, 5), LAMP)
		_place(Vector2i(lamp_x, 8), LAMP)
	for bench_x in [6, 13, 27]:
		_place(Vector2i(bench_x, 8), BENCH)
	for gap_x in [6, 13, 20, 27]:
		_place(Vector2i(gap_x, 2), TREE)
	for gap_x in [6, 13]:
		_place(Vector2i(gap_x, 11), TREE)
	_prop(Vector2i(21, 11), SIGN)
	_blocked[Vector2i(21, 11)] = true
	for y in range(20, 26):
		for x in range(2, 8):
			if (x + y) % 2 == 0:
				_place(Vector2i(x, y), TREE)
		for x in range(28, 34):
			if (x + y) % 2 == 0:
				_place(Vector2i(x, y), TREE)
	for x in range(2, MAP_W - 2, 3):
		if x == 24 or x == 23 or x == 25:
			continue
		_place(Vector2i(x, 16), TREE)
	_place(Vector2i(23, 20), BENCH)
	_place(Vector2i(25, 22), BENCH)
	_place(Vector2i(23, 24), BENCH)
	_place(Vector2i(8, 19), HEDGE)
	_place(Vector2i(9, 19), HEDGE_END)
	_place(Vector2i(8, 20), PLANTER)
	_place(Vector2i(10, 19), HEDGE)


func _place(cell: Vector2i, tile: Vector2i) -> void:
	if _blocked.has(cell):
		return
	_prop(cell, tile)
	_blocked[cell] = true
