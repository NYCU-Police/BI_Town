extends Node2D

## Must match backend/app/simulation/poi.py. These points are the ground
## in front of each door, so an idle resident stands on them as-is.
const POIS := {
	"mina_home": Vector2(56, 96),
	"alex_home": Vector2(168, 96),
	"rin_home": Vector2(280, 96),
	"cafe": Vector2(392, 96),
	"store": Vector2(504, 96),
	"office": Vector2(56, 144),
	"library": Vector2(168, 144),
	"plaza": Vector2(280, 192),
	"park": Vector2(392, 320),
}

const POI_NAMES := {
	"mina_home": "Mina 的家",
	"alex_home": "Alex 的家",
	"rin_home": "Rin 的家",
	"cafe": "咖啡廳",
	"store": "便利商店",
	"office": "辦公室",
	"library": "圖書館",
	"plaza": "廣場",
	"park": "公園",
}

const POI_PICK_RADIUS := 56.0
const AGENT_PICK_RADIUS := 36.0

@export var npc_scene: PackedScene

var _npcs: Dictionary = {}
var _you := ""
var _destination := ""
var _hover_id := ""
var _hover_label: Label
var _destination_mark: Node2D
var _place_labels: Dictionary = {}
var _show_content_ids := false


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	var pois_root := get_node_or_null("POIs")
	if pois_root == null:
		push_error("World is missing the POIs node")
		return
	for poi_id in POIS:
		var node := pois_root.get_node_or_null(poi_id) as Node2D
		if node == null:
			node = Node2D.new()
			node.name = poi_id
			pois_root.add_child(node)
		node.position = POIS[poi_id]
		var sprite := node.get_node_or_null("Sprite") as Sprite2D
		if sprite == null:
			sprite = Sprite2D.new()
			sprite.name = "Sprite"
			node.add_child(sprite)
		sprite.texture_filter = TEXTURE_FILTER_NEAREST
		VisualBinder.apply(sprite, node, "poi.%s" % poi_id)
		_place_labels[poi_id] = _make_place_label(poi_id)
		var ring := Line2D.new()
		ring.name = "HoverRing"
		ring.width = 2.0
		ring.closed = true
		ring.visible = false
		ring.default_color = Color(1, 0.95, 0.72)
		ring.points = _circle_points(18.0, 20)
		node.add_child(ring)
	_place_cafe_bread()
	_hover_label = Label.new()
	_hover_label.name = "PoiHover"
	_hover_label.visible = false
	_hover_label.z_index = 40
	_hover_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hover_label.size = Vector2(120, 18)
	_hover_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hover_label.add_theme_font_size_override("font_size", 12)
	_hover_label.add_theme_color_override("font_color", Color.WHITE)
	_hover_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 1))
	_hover_label.add_theme_constant_override("outline_size", 5)
	add_child(_hover_label)
	_destination_mark = _make_destination_mark()
	add_child(_destination_mark)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key := event as InputEventKey
		if key.pressed and not key.echo and key.keycode == KEY_F3:
			_show_content_ids = not _show_content_ids
			_refresh_place_names()
			get_viewport().set_input_as_handled()


func _process(_delta: float) -> void:
	_update_hover()


func agent_at(world_pos: Vector2) -> String:
	var nearest := ""
	var best := AGENT_PICK_RADIUS
	for agent_id in _npcs:
		var npc := _npcs[agent_id] as Node2D
		if npc == null:
			continue
		var distance := world_pos.distance_to(npc.global_position)
		if distance <= best:
			best = distance
			nearest = str(agent_id)
	return nearest


func poi_at(world_pos: Vector2) -> String:
	var nearest := ""
	var best := POI_PICK_RADIUS
	for poi_id in POIS:
		var distance := world_pos.distance_to(POIS[poi_id])
		if distance <= best:
			best = distance
			nearest = poi_id
	return nearest


func show_destination(poi_id: String) -> void:
	if not POIS.has(poi_id):
		return
	_destination = poi_id
	_destination_mark.position = POIS[poi_id]
	_destination_mark.visible = true


func clear_destination() -> void:
	_destination = ""
	_destination_mark.visible = false


func local_player_position() -> Vector2:
	return npc_position(_you)


func _sync_clock(data: Dictionary) -> void:
	if not data.has("time"):
		return
	var clock := get_node_or_null("DayNight")
	if clock != null and clock.has_method("set_clock"):
		clock.set_clock(str(data["time"]))


func apply_snapshot(data: Dictionary) -> void:
	_sync_clock(data)
	_you = str(data.get("you", ""))
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("world_snapshot.agents is not an array")
		return
	var seen := {}
	for agent in agents:
		if typeof(agent) == TYPE_DICTIONARY:
			var agent_id := str(agent.get("id", ""))
			if not agent_id.is_empty():
				seen[agent_id] = true
			_upsert_npc(agent, true)
	var stale: Array[String] = []
	for agent_id in _npcs.keys():
		if not seen.has(agent_id):
			stale.append(str(agent_id))
	for agent_id in stale:
		_remove_npc(agent_id)
	_separate_overlaps(true)


func apply_agent_update(data: Dictionary) -> void:
	_sync_clock(data)
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("agent_update.agents is not an array")
		return
	var removed: Variant = data.get("removed", [])
	if typeof(removed) == TYPE_ARRAY:
		for agent_id in removed:
			_remove_npc(str(agent_id))
	for agent in agents:
		if typeof(agent) == TYPE_DICTIONARY:
			_upsert_npc(agent, false)
	_separate_overlaps(false)


func show_speech(agent_id: String, content: String) -> void:
	if not _npcs.has(agent_id):
		return
	var npc: Node = _npcs[agent_id]
	if npc.has_method("show_speech"):
		npc.show_speech(content)


func present_event(data: Dictionary) -> void:
	var agent_id := str(data.get("agent_id", ""))
	if not _npcs.has(agent_id):
		return
	var npc: Node = _npcs[agent_id]
	if npc.has_method("react"):
		npc.react(str(data.get("event", "")), str(data.get("item", "")))


func _place_cafe_bread() -> void:
	var cafe := get_node_or_null("POIs/cafe") as Node2D
	if cafe == null:
		return
	var host := Node2D.new()
	host.name = "Bread"
	host.position = Vector2(14, 8)
	var sprite := Sprite2D.new()
	sprite.name = "Sprite"
	host.add_child(sprite)
	cafe.add_child(host)
	VisualBinder.apply(sprite, host, "item.bread")


func npc_position(agent_id: String) -> Vector2:
	if not _npcs.has(agent_id):
		return Vector2.INF
	return (_npcs[agent_id] as Node2D).global_position


func _separate_overlaps(snap: bool) -> void:
	var groups: Dictionary = {}
	for agent_id in _npcs:
		var npc: Node = _npcs[agent_id]
		if not npc.has_method("server_anchor"):
			continue
		var anchor: Vector2 = npc.server_anchor()
		var key := "%s,%s" % [snappedf(anchor.x, 1.0), snappedf(anchor.y, 1.0)]
		if not groups.has(key):
			groups[key] = []
		(groups[key] as Array).append(str(agent_id))
	for key in groups:
		var ids: Array = groups[key]
		ids.sort()
		for index in ids.size():
			var npc: Node = _npcs[ids[index]]
			if npc.has_method("set_cluster_slot"):
				npc.set_cluster_slot(index, ids.size(), snap)


func _remove_npc(agent_id: String) -> void:
	if agent_id.is_empty() or not _npcs.has(agent_id):
		return
	var npc: Node = _npcs[agent_id]
	_npcs.erase(agent_id)
	npc.queue_free()


func _upsert_npc(agent: Dictionary, snap: bool) -> void:
	if npc_scene == null:
		push_error("World.npc_scene is not assigned")
		return

	var agent_id := str(agent.get("id", ""))
	if agent_id.is_empty():
		push_error("Agent payload missing id: %s" % str(agent))
		return

	var npc: Node2D
	if _npcs.has(agent_id):
		npc = _npcs[agent_id]
	else:
		npc = npc_scene.instantiate() as Node2D
		if npc == null:
			push_error("npc.tscn root must be Node2D")
			return
		add_child(npc)
		_npcs[agent_id] = npc

	if not npc.has_method("update_from_server"):
		push_error("NPC missing update_from_server()")
		return
	npc.update_from_server(agent, snap)
	if npc.has_method("set_local_player"):
		npc.set_local_player(agent_id == _you)
	if agent_id == _you and _destination == str(agent.get("location", "")):
		if str(agent.get("state", "")) != "walking":
			clear_destination()
	if npc.has_method("set_stand_offset"):
		npc.set_stand_offset(Vector2.ZERO, snap)


func _update_hover() -> void:
	if _hover_label == null:
		return
	var next := ""
	if not _pointer_over_chrome():
		next = poi_at(get_global_mouse_position())
	if next != _hover_id:
		_set_hover(next)


func _set_hover(poi_id: String) -> void:
	var pois_root := get_node_or_null("POIs")
	if _hover_id != "" and pois_root != null:
		var previous := pois_root.get_node_or_null(_hover_id)
		if previous != null:
			var old_ring := previous.get_node_or_null("HoverRing")
			if old_ring != null:
				old_ring.visible = false
			var old_sprite := previous.get_node_or_null("Sprite") as CanvasItem
			if old_sprite != null:
				old_sprite.modulate = Color.WHITE
	_hover_id = poi_id
	if poi_id.is_empty() or pois_root == null:
		_hover_label.visible = false
		return
	var node := pois_root.get_node_or_null(poi_id)
	if node == null:
		_hover_label.visible = false
		return
	var ring := node.get_node_or_null("HoverRing")
	if ring != null:
		ring.visible = true
	var sprite := node.get_node_or_null("Sprite") as CanvasItem
	if sprite != null:
		sprite.modulate = Color(1.45, 1.38, 1.05)
	_hover_label.text = _place_caption(poi_id)
	var anchor: Vector2 = POIS[poi_id]
	_hover_label.position = anchor + Vector2(-60, -54)
	_hover_label.visible = true


func _place_caption(poi_id: String) -> String:
	if _show_content_ids:
		return "poi.%s" % poi_id
	return str(POI_NAMES.get(poi_id, poi_id))


func _refresh_place_names() -> void:
	for poi_id in _place_labels:
		var label := _place_labels[poi_id] as Label
		if label != null:
			label.text = _place_caption(str(poi_id))
	if _hover_label != null and not _hover_id.is_empty():
		_hover_label.text = _place_caption(_hover_id)


func _make_place_label(poi_id: String) -> Label:
	var label := Label.new()
	label.name = "PlaceName"
	label.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	label.z_index = 30
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.text = _place_caption(poi_id)
	label.position = POIS[poi_id] + Vector2(-60, -68)
	label.size = Vector2(120, 16)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 12)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 1))
	label.add_theme_constant_override("outline_size", 2)
	add_child(label)
	return label


func _pointer_over_chrome() -> bool:
	var view := get_viewport().get_visible_rect().size
	var mouse := get_viewport().get_mouse_position()
	return mouse.y >= view.y - 168.0 and mouse.x < 660.0


func _make_destination_mark() -> Node2D:
	var mark := Node2D.new()
	mark.name = "Destination"
	mark.z_index = 25
	mark.visible = false
	var pin := Polygon2D.new()
	pin.color = Color(1.0, 0.78, 0.15)
	pin.polygon = PackedVector2Array([
		Vector2(0, -2),
		Vector2(-8, -18),
		Vector2(-3, -18),
		Vector2(-3, -30),
		Vector2(3, -30),
		Vector2(3, -18),
		Vector2(8, -18),
	])
	mark.add_child(pin)
	return mark


func _circle_points(radius: float, count: int) -> PackedVector2Array:
	var points := PackedVector2Array()
	for index in count:
		var angle := TAU * float(index) / float(count)
		points.append(Vector2(cos(angle), sin(angle)) * radius)
	return points
