extends TileMapLayer

## Visual only. Place ids and coordinates live in world.gd and must match
## backend/app/simulation/poi.py. Tiles are the Ninja Adventure pack, 16×16,
## no spacing. Building lots stay on the same origins as the previous map.
## The pack has no lamp, bench, or fountain sprite, so those are not drawn.
## The plaza pool is water tiles.

const TILE := 16
const MAP_W := 36
const MAP_H := 28

const GRASS := Vector2i(11, 12)
const GRASS_ALT := Vector2i(2, 12)
const ROAD := Vector2i(14, 18)
const WALK := Vector2i(12, 15)
const WATER := Vector2i(1, 1)

const _FLOOR := "res://assets/packs/default/tiles/floor.png"
const _DETAIL := "res://assets/packs/default/tiles/floor_detail.png"
const _HOUSE := "res://assets/packs/default/tiles/house.png"
const _NATURE := "res://assets/packs/default/tiles/nature.png"
const _WATER := "res://assets/packs/default/tiles/water.png"

var _floor_source := 0
var _detail_source := 0
var _house_source := 0
var _nature_source := 0
var _water_source := 0
var _detail: TileMapLayer
var _water_layer: TileMapLayer
var _objects: TileMapLayer
var _lights: Node2D
var _glow: Texture2D
var _ground: Dictionary = {}
var _blocked: Dictionary = {}


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	z_index = 0
	y_sort_enabled = false
	_detail = get_node_or_null("../Detail") as TileMapLayer
	_water_layer = get_node_or_null("../Water") as TileMapLayer
	_objects = get_node_or_null("../Objects") as TileMapLayer
	_prepare_layer(_detail, 0, false)
	_prepare_layer(_water_layer, 0, false)
	_prepare_layer(_objects, 1, true)
	if _water_layer != null:
		var flow := ShaderMaterial.new()
		flow.shader = load("res://shaders/water.gdshader")
		_water_layer.material = flow
	_lights = get_parent().get_node_or_null("NightLights") as Node2D
	if _lights == null:
		push_error("World is missing the NightLights node")
		_lights = Node2D.new()
	_rebuild()


func _prepare_layer(layer: TileMapLayer, layer_z: int, sort_y: bool) -> void:
	if layer == null:
		return
	layer.texture_filter = TEXTURE_FILTER_NEAREST
	layer.z_index = layer_z
	layer.y_sort_enabled = sort_y


func _rebuild() -> void:
	var tileset := TileSet.new()
	tileset.tile_size = Vector2i(TILE, TILE)
	tileset.uv_clipping = true
	_floor_source = _add_source(tileset, _FLOOR, [GRASS, GRASS_ALT, ROAD, WALK])
	_detail_source = _add_source(tileset, _DETAIL, [
		Vector2i(2, 2), Vector2i(5, 2), Vector2i(6, 2), Vector2i(7, 2),
	])
	_house_source = _add_source(tileset, _HOUSE, [])
	for building in _buildings():
		_create_sorted(tileset, _house_source, building[1], building[2])
	_nature_source = _add_source(tileset, _NATURE, [])
	for tree_atlas in [Vector2i(0, 0), Vector2i(2, 0), Vector2i(6, 0)]:
		_create_sorted(tileset, _nature_source, tree_atlas, Vector2i(2, 2))
	_water_source = _add_source(tileset, _WATER, [WATER])
	tile_set = tileset
	clear()
	if _detail != null:
		_detail.tile_set = tileset
		_detail.clear()
	if _water_layer != null:
		_water_layer.tile_set = tileset
		_water_layer.clear()
	if _objects != null:
		_objects.tile_set = tileset
		_objects.clear()
	for child in _lights.get_children():
		child.free()
	_ground.clear()
	_blocked.clear()
	_paint_base()
	_paint_roads()
	_paint_park()
	_paint_plaza()
	_paint_buildings()
	_paint_trees()
	_paint_pool()
	_paint_flowers()
	for cell in _ground:
		set_cell(cell, _floor_source, _ground[cell])


func _add_source(tileset: TileSet, path: String, coords: Array) -> int:
	var atlas := TileSetAtlasSource.new()
	atlas.texture = load(path)
	atlas.texture_region_size = Vector2i(TILE, TILE)
	for coord in coords:
		atlas.create_tile(coord)
	return tileset.add_source(atlas)


func _create_sorted(tileset: TileSet, source_id: int, atlas_coords: Vector2i, size: Vector2i) -> void:
	var atlas := tileset.get_source(source_id) as TileSetAtlasSource
	atlas.create_tile(atlas_coords, size)
	var data := atlas.get_tile_data(atlas_coords, 0)
	data.y_sort_origin = size.y * TILE


func _buildings() -> Array:
	# origin, atlas top-left, size. Lots match the previous map.
	return [
		[Vector2i(1, 1), Vector2i(0, 0), Vector2i(4, 3)],
		[Vector2i(8, 1), Vector2i(12, 0), Vector2i(4, 3)],
		[Vector2i(15, 1), Vector2i(23, 0), Vector2i(3, 3)],
		[Vector2i(22, 1), Vector2i(16, 0), Vector2i(3, 3)],
		[Vector2i(29, 1), Vector2i(4, 0), Vector2i(4, 3)],
		[Vector2i(1, 9), Vector2i(8, 0), Vector2i(4, 3)],
		[Vector2i(8, 9), Vector2i(0, 11), Vector2i(3, 3)],
	]


func _paint_base() -> void:
	for y in MAP_H:
		for x in MAP_W:
			_set_ground(Vector2i(x, y), GRASS)


func _fill_rect(origin: Vector2i, size: Vector2i, tile: Vector2i) -> void:
	for y in size.y:
		for x in size.x:
			_set_ground(origin + Vector2i(x, y), tile)


func _set_ground(cell: Vector2i, tile: Vector2i) -> void:
	if tile == GRASS and (cell.x * 3 + cell.y * 5) % 5 == 0:
		_ground[cell] = GRASS_ALT
	else:
		_ground[cell] = tile


func _paint_roads() -> void:
	_fill_rect(Vector2i(0, 5), Vector2i(MAP_W, 1), WALK)
	_fill_rect(Vector2i(0, 6), Vector2i(MAP_W, 2), ROAD)
	_fill_rect(Vector2i(0, 8), Vector2i(MAP_W, 1), WALK)
	for column in [3, 10, 17, 24, 31]:
		for y in [6, 7]:
			_set_ground(Vector2i(column, y), ROAD)
	for y in range(9, 16):
		_set_ground(Vector2i(24, y), ROAD)


func _paint_park() -> void:
	for y in range(16, MAP_H):
		for x in range(1, MAP_W - 1):
			_set_ground(Vector2i(x, y), GRASS)
	var path: Array[Vector2i] = [
		Vector2i(24, 16), Vector2i(24, 17), Vector2i(23, 18),
		Vector2i(22, 19), Vector2i(23, 20), Vector2i(24, 20),
		Vector2i(24, 21), Vector2i(25, 22), Vector2i(26, 23),
		Vector2i(25, 24), Vector2i(24, 25), Vector2i(23, 26),
	]
	for cell in path:
		_set_ground(cell, WALK)
		_blocked[cell] = true


func _paint_plaza() -> void:
	for y in range(9, 16):
		for x in range(15, 35):
			if x == 24:
				continue
			_set_ground(Vector2i(x, y), WALK)


func _paint_buildings() -> void:
	for building in _buildings():
		var origin: Vector2i = building[0]
		var atlas_coords: Vector2i = building[1]
		var size: Vector2i = building[2]
		if _objects != null:
			_objects.set_cell(origin, _house_source, atlas_coords)
		for y in size.y:
			for x in size.x:
				_blocked[origin + Vector2i(x, y)] = true
		_window_light(origin, size)


func _window_light(origin: Vector2i, size: Vector2i) -> void:
	var cell := origin + Vector2i(maxi(size.x >> 1, 1), maxi((size.y >> 1) - 1, 0))
	var light := PointLight2D.new()
	light.texture = _glow_texture()
	light.texture_scale = 1.4
	light.energy = 0.0
	light.color = Color(1.0, 0.82, 0.55)
	light.position = Vector2(cell) * float(TILE) + Vector2(TILE * 0.5, TILE * 0.5)
	light.add_to_group("night_light")
	_lights.add_child(light)


func _glow_texture() -> Texture2D:
	if _glow != null:
		return _glow
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	var center := Vector2(31.5, 31.5)
	for y in 64:
		for x in 64:
			var falloff := clampf(1.0 - Vector2(x, y).distance_to(center) / 31.5, 0.0, 1.0)
			image.set_pixel(x, y, Color(1, 1, 1, falloff * falloff))
	_glow = ImageTexture.create_from_image(image)
	return _glow


func _paint_trees() -> void:
	var trees: Array[Vector2i] = [
		Vector2i(6, 2), Vector2i(13, 2), Vector2i(20, 2), Vector2i(27, 2),
		Vector2i(6, 11), Vector2i(13, 11),
		Vector2i(3, 18), Vector2i(4, 19), Vector2i(2, 21), Vector2i(5, 22),
		Vector2i(3, 23), Vector2i(6, 24), Vector2i(4, 26),
		Vector2i(30, 18), Vector2i(32, 19), Vector2i(29, 21), Vector2i(33, 22),
		Vector2i(31, 24), Vector2i(28, 25), Vector2i(33, 26),
		Vector2i(19, 22), Vector2i(20, 24), Vector2i(18, 26), Vector2i(27, 20),
		Vector2i(8, 17), Vector2i(14, 18), Vector2i(31, 17),
	]
	var kinds: Array[Vector2i] = [Vector2i(0, 0), Vector2i(2, 0), Vector2i(6, 0)]
	for index in trees.size():
		var cell: Vector2i = trees[index]
		var origin := Vector2i(cell.x, cell.y - 1)
		if not _fits(origin, Vector2i(2, 2)):
			continue
		if _objects != null:
			_objects.set_cell(origin, _nature_source, kinds[index % kinds.size()])
		for y in 2:
			for x in 2:
				_blocked[origin + Vector2i(x, y)] = true


func _fits(origin: Vector2i, size: Vector2i) -> bool:
	for y in size.y:
		for x in size.x:
			var cell := origin + Vector2i(x, y)
			if cell.x < 0 or cell.y < 0 or cell.x >= MAP_W or cell.y >= MAP_H:
				return false
			if _blocked.has(cell):
				return false
	return true


func _paint_pool() -> void:
	if _water_layer == null:
		return
	for cell in [Vector2i(19, 12), Vector2i(20, 12), Vector2i(19, 13), Vector2i(20, 13)]:
		_water_layer.set_cell(cell, _water_source, WATER)
		_blocked[cell] = true


func _paint_flowers() -> void:
	if _detail == null:
		return
	var kinds: Array[Vector2i] = [
		Vector2i(2, 2), Vector2i(5, 2), Vector2i(6, 2), Vector2i(7, 2),
	]
	for cell in _ground:
		var tile: Vector2i = _ground[cell]
		if tile != GRASS and tile != GRASS_ALT:
			continue
		if _blocked.has(cell):
			continue
		if (cell.x * 5 + cell.y * 3) % 11 != 0:
			continue
		_detail.set_cell(cell, _detail_source, kinds[(cell.x + cell.y) % kinds.size()])
