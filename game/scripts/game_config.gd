extends RefCounted

const SUPPORTED_VERSION := 1

static var ready := false
static var version := 0
static var poi_pick_radius := 0.0
static var agent_pick_radius := 0.0
static var need_low := 0
static var eat_restore := 0
static var _names: Dictionary = {}
static var _positions: Dictionary = {}
static var _items: Dictionary = {}


static func apply(data: Dictionary) -> bool:
	var incoming := int(data.get("version", 0))
	if incoming != SUPPORTED_VERSION:
		push_error("game_config version %s is not supported" % incoming)
		return false
	var pois: Variant = data.get("pois", [])
	if typeof(pois) != TYPE_ARRAY:
		push_error("game_config pois is not a list")
		return false
	var names := {}
	var positions := {}
	for row in pois:
		if typeof(row) != TYPE_DICTIONARY:
			continue
		var poi_id := str(row.get("id", ""))
		if poi_id.is_empty():
			continue
		names[poi_id] = str(row.get("name", poi_id))
		positions[poi_id] = Vector2(float(row.get("x", 0.0)), float(row.get("y", 0.0)))
	var items := {}
	var raw_items: Variant = data.get("items", [])
	if typeof(raw_items) == TYPE_ARRAY:
		for row in raw_items:
			if typeof(row) != TYPE_DICTIONARY:
				continue
			var item_id := str(row.get("id", ""))
			if item_id.is_empty():
				continue
			items[item_id] = {
				"name": str(row.get("name", item_id)),
				"food": bool(row.get("food", false)),
			}
	_names = names
	_positions = positions
	_items = items
	version = incoming
	poi_pick_radius = float(data.get("poi_pick_radius", 0.0))
	agent_pick_radius = float(data.get("agent_pick_radius", 0.0))
	need_low = int(data.get("need_low", 0))
	eat_restore = int(data.get("eat_restore", 0))
	ready = true
	return true


static func place_ids() -> Array:
	return _positions.keys()


static func place_label(poi_id: String) -> String:
	return str(_names.get(poi_id, poi_id))


static func place_position(poi_id: String) -> Vector2:
	return _positions.get(poi_id, Vector2.ZERO)


static func has_place(poi_id: String) -> bool:
	return _positions.has(poi_id)


static func has_item(item_id: String) -> bool:
	return _items.has(item_id)


static func item_name(item_id: String) -> String:
	var row: Variant = _items.get(item_id, {})
	if typeof(row) != TYPE_DICTIONARY:
		return item_id
	return str(row.get("name", item_id))


static func is_food(item_id: String) -> bool:
	var row: Variant = _items.get(item_id, {})
	if typeof(row) != TYPE_DICTIONARY:
		return false
	return bool(row.get("food", false))
