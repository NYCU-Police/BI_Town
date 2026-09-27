extends TileMapLayer

## Visual only. Place ids and coordinates live in world.gd and must match
## backend/app/simulation/poi.py. Tiles are Kenney RPG Urban Pack, 16×16
## with 1px spacing.

const TILE := 16
const MAP_W := 60
const MAP_H := 40

const GRASS := Vector2i(1, 1)
const GRASS_B := Vector2i(5, 1)
const ROAD := Vector2i(9, 1)
const WALK := Vector2i(1, 4)
const PLAZA := Vector2i(5, 4)
const TREE := Vector2i(21, 10)
const BENCH := Vector2i(1, 10)
const LAMP := Vector2i(0, 6)
const FLOWER_A := Vector2i(6, 10)
const FLOWER_B := Vector2i(7, 10)
const WINDOW := Vector2i(11, 10)
const DOOR_HOME := Vector2i(13, 11)
const DOOR_CAFE := Vector2i(14, 10)
const DOOR_GLASS := Vector2i(15, 10)
const AWNING := Vector2i(6, 8)
const GLASS := Vector2i(9, 14)
const SIGN := Vector2i(11, 12)

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
		GRASS, GRASS_B, ROAD, WALK, PLAZA, TREE, BENCH, LAMP,
		FLOWER_A, FLOWER_B, WINDOW, DOOR_HOME, DOOR_CAFE, DOOR_GLASS,
		AWNING, GLASS, SIGN,
		Vector2i(16, 0), Vector2i(17, 0), Vector2i(20, 0),
		Vector2i(16, 2), Vector2i(17, 2), Vector2i(20, 2),
		Vector2i(16, 4), Vector2i(17, 4), Vector2i(20, 4),
		Vector2i(16, 6), Vector2i(17, 6), Vector2i(20, 6),
		Vector2i(12, 0), Vector2i(13, 0), Vector2i(15, 0),
		Vector2i(12, 1), Vector2i(13, 1), Vector2i(15, 1),
		Vector2i(8, 13), Vector2i(8, 15),
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
	_paint_buildings()
	_paint_plaza_and_park()
	_paint_props()
	for cell in _ground:
		set_cell(cell, _source_id, _ground[cell])


func _paint_base() -> void:
	for y in MAP_H:
		for x in MAP_W:
			var cell := Vector2i(x, y)
			_ground[cell] = GRASS_B if (x + y) % 2 == 0 else GRASS


func _fill_rect(origin: Vector2i, size: Vector2i, tile: Vector2i) -> void:
	for y in size.y:
		for x in size.x:
			_ground[origin + Vector2i(x, y)] = tile


func _paint_roads() -> void:
	# North street under the homes, south street in front of the lower doors,
	# and verticals on each door column so the network reaches every place.
	_fill_rect(Vector2i(1, 6), Vector2i(56, 1), WALK)
	_fill_rect(Vector2i(1, 7), Vector2i(56, 2), ROAD)
	_fill_rect(Vector2i(1, 9), Vector2i(56, 1), WALK)
	_fill_rect(Vector2i(1, 18), Vector2i(56, 2), ROAD)
	_fill_rect(Vector2i(1, 20), Vector2i(56, 1), WALK)
	for column in [4, 14, 24, 36, 50]:
		for y in range(7, 20):
			_ground[Vector2i(column, y)] = ROAD
			if column > 0:
				var left := Vector2i(column - 1, y)
				if _ground.get(left) != ROAD:
					_ground[left] = WALK
		# Park path continues south from the store column.
		if column == 50:
			for y in range(20, 31):
				_ground[Vector2i(column, y)] = ROAD


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
	var red_roof := _row(Vector2i(16, 0), Vector2i(17, 0), Vector2i(20, 0), 6)
	var red_wall := _row(Vector2i(16, 2), Vector2i(17, 2), Vector2i(20, 2), 6)
	var red_windows := red_wall.duplicate()
	red_windows[2] = WINDOW
	red_windows[4] = WINDOW
	var red_door := red_wall.duplicate()
	red_door[2] = DOOR_HOME
	var orange_roof := _row(Vector2i(16, 4), Vector2i(17, 4), Vector2i(20, 4), 6)
	var orange_wall := _row(Vector2i(16, 6), Vector2i(17, 6), Vector2i(20, 6), 6)
	var orange_windows := orange_wall.duplicate()
	orange_windows[1] = WINDOW
	orange_windows[4] = WINDOW
	var cafe_door := orange_wall.duplicate()
	cafe_door[2] = DOOR_CAFE
	var store_door := orange_wall.duplicate()
	store_door[2] = DOOR_GLASS
	store_door[1] = GLASS
	store_door[3] = GLASS
	var grey_roof := _row(Vector2i(12, 0), Vector2i(13, 0), Vector2i(15, 0), 6)
	var grey_wall := _row(Vector2i(12, 1), Vector2i(13, 1), Vector2i(15, 1), 6)
	var office_windows := grey_wall.duplicate()
	office_windows[4] = WINDOW
	var office_door := grey_wall.duplicate()
	office_door[2] = DOOR_GLASS
	var library_windows := grey_wall.duplicate()
	library_windows[1] = WINDOW
	library_windows[3] = WINDOW
	library_windows[4] = WINDOW
	var library_door := grey_wall.duplicate()
	library_door[2] = DOOR_CAFE

	# North row: door on the south edge, resident stands on the sidewalk below.
	_stamp(Vector2i(2, 2), [red_roof, red_wall, red_windows, red_door])
	_stamp(Vector2i(12, 2), [red_roof, red_wall, red_windows, red_door])
	_stamp(Vector2i(22, 2), [red_roof, red_wall, red_windows, red_door])
	_stamp(Vector2i(34, 2), [orange_roof, orange_wall, orange_windows, cafe_door])
	_prop(Vector2i(36, 4), AWNING)
	_stamp(Vector2i(48, 2), [orange_roof, orange_windows, orange_wall, store_door])
	_prop(Vector2i(50, 4), AWNING)
	# South row: door on the north edge, so the walk down the street stops
	# on the sidewalk and does not cross the building.
	_stamp(Vector2i(2, 21), [office_door, office_windows, grey_wall, grey_roof])
	_stamp(Vector2i(12, 21), [library_door, library_windows, grey_wall, grey_roof])


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


func _paint_plaza_and_park() -> void:
	_fill_rect(Vector2i(30, 16), Vector2i(14, 8), PLAZA)
	# Keep the vertical road and the south sidewalk readable through the plaza.
	for y in range(16, 24):
		_ground[Vector2i(36, y)] = ROAD if y < 20 else WALK
	_prop(Vector2i(36, 17), SIGN)
	_blocked[Vector2i(36, 17)] = true
	for y in range(26, 38):
		for x in range(42, 59):
			if _ground.get(Vector2i(x, y)) == ROAD:
				continue
			if (x + y) % 3 == 0:
				_prop(Vector2i(x, y), TREE)
				_blocked[Vector2i(x, y)] = true
			elif (x * 2 + y) % 5 == 0:
				_prop(Vector2i(x, y), FLOWER_A if x % 2 == 0 else FLOWER_B)
				_blocked[Vector2i(x, y)] = true
	for bench_y in [27, 32, 36]:
		_prop(Vector2i(46, bench_y), BENCH)
		_prop(Vector2i(54, bench_y), BENCH)


func _paint_props() -> void:
	for y in MAP_H:
		for x in MAP_W:
			var cell := Vector2i(x, y)
			if _blocked.has(cell):
				continue
			var kind: Vector2i = _ground.get(cell, GRASS)
			if kind == GRASS or kind == GRASS_B:
				if y <= 1 or (x * 3 + y * 5) % 7 == 0:
					_prop(cell, TREE)
					_blocked[cell] = true
				elif (x * 2 + y) % 9 == 0:
					_prop(cell, FLOWER_A if (x + y) % 2 == 0 else FLOWER_B)
					_blocked[cell] = true
			elif kind == WALK and x % 6 == 1 and y != 6 and y != 20:
				_prop(cell, LAMP)
			elif kind == WALK and x % 8 == 3 and y == 9:
				_prop(cell, BENCH)
			elif kind == PLAZA and x % 5 == 0 and y % 3 == 0:
				_prop(cell, BENCH if x % 2 == 0 else FLOWER_B)
