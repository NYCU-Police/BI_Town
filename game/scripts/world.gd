extends Node2D

const _Places := preload("res://scripts/place_names.gd")
const _Rules := preload("res://scripts/game_config.gd")
const _Circle := preload("res://scripts/circle_points.gd")

@export var npc_scene: PackedScene

var _npcs: Dictionary = {}
var _you := ""
var _destination := ""
var _hover_id := ""
var _hover_label: Label
var _destination_mark: Node2D
var _place_labels: Dictionary = {}
var _show_content_ids := false
var _notice_label: Label
var _link_up := false
var _configured := false


func playable() -> bool:
	return _link_up and _configured


func set_link_up(online: bool) -> void:
	_link_up = online
	if not online:
		_configured = false


func apply_game_config(data: Dictionary) -> bool:
	if not _Rules.apply(data):
		return false
	var pois_root := get_node_or_null("POIs")
	if pois_root == null:
		push_error("World is missing the POIs node")
		return false
	var seen := {}
	for poi_id in _Rules.place_ids():
		var place_id := str(poi_id)
		seen[place_id] = true
		var node := pois_root.get_node_or_null(place_id) as Node2D
		if node == null:
			node = Node2D.new()
			node.name = place_id
			pois_root.add_child(node)
		node.position = _Rules.place_position(place_id)
		var sprite := node.get_node_or_null("Sprite") as Sprite2D
		if sprite == null:
			sprite = Sprite2D.new()
			sprite.name = "Sprite"
			node.add_child(sprite)
			sprite.texture_filter = TEXTURE_FILTER_NEAREST
			VisualBinder.apply(sprite, node, "poi.%s" % place_id)
		var ring := node.get_node_or_null("HoverRing") as Line2D
		if ring == null:
			ring = Line2D.new()
			ring.name = "HoverRing"
			ring.width = 2.0
			ring.closed = true
			ring.visible = false
			ring.default_color = _ui_color("poi_ring")
			ring.points = _Circle.points(18.0, 20)
			node.add_child(ring)
		if _place_labels.has(place_id):
			var existing := _place_labels[place_id] as Label
			if existing != null:
				existing.position = _Rules.place_position(place_id) + Vector2(-60, -68)
				existing.text = _place_caption(place_id)
		else:
			_place_labels[place_id] = _make_place_label(place_id)
	for child in pois_root.get_children():
		if seen.has(str(child.name)):
			continue
		if _place_labels.has(child.name):
			var stale: Node = _place_labels[child.name]
			_place_labels.erase(child.name)
			stale.queue_free()
		child.queue_free()
	_place_cafe_bread()
	_position_notice()
	_configured = _link_up
	var camera := get_node_or_null("Camera")
	if camera != null and camera.has_method("frame_once") and _Rules.has_place("plaza"):
		camera.frame_once(_Rules.place_position("plaza"))
	return true


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	_hover_label = Label.new()
	_hover_label.name = "PoiHover"
	_hover_label.visible = false
	_hover_label.z_index = 40
	_hover_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hover_label.size = Vector2(120, 18)
	_hover_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_map_label(_hover_label)
	add_child(_hover_label)
	_destination_mark = _make_destination_mark()
	add_child(_destination_mark)
	_notice_label = Label.new()
	_notice_label.name = "PlazaNotice"
	_notice_label.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_notice_label.z_index = 30
	_notice_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_notice_label.size = Vector2(220, 48)
	_notice_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_notice_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_style_map_label(_notice_label)
	add_child(_notice_label)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key := event as InputEventKey
		if key.pressed and not key.echo and key.keycode == KEY_F3:
			_show_content_ids = not _show_content_ids
			_refresh_place_names()
			get_viewport().set_input_as_handled()


func _process(_delta: float) -> void:
	_update_hover()
	_stack_nameplates()


func agent_at(world_pos: Vector2) -> String:
	if not _Rules.ready:
		return ""
	var nearest := ""
	var best := _Rules.agent_pick_radius
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
	if not _Rules.ready:
		return ""
	var nearest := ""
	var best := _Rules.poi_pick_radius
	for poi_id in _Rules.place_ids():
		var place_id := str(poi_id)
		var distance := world_pos.distance_to(_Rules.place_position(place_id))
		if distance <= best:
			best = distance
			nearest = place_id
	return nearest


func show_destination(poi_id: String) -> void:
	if not _Rules.has_place(poi_id):
		return
	_destination = poi_id
	_destination_mark.position = _Rules.place_position(poi_id)
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


func set_notice(text: String) -> void:
	if _notice_label != null:
		_notice_label.text = text
		_position_notice()


func _position_notice() -> void:
	if _notice_label == null or not _Rules.has_place("plaza"):
		return
	_notice_label.position = _Rules.place_position("plaza") + Vector2(-110, 18)


func apply_snapshot(data: Dictionary) -> void:
	_sync_clock(data)
	set_notice(str(data.get("notice", "")))
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
	if data.has("notice"):
		set_notice(str(data.get("notice", "")))
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


func show_conversing(player_id: String, resident_id: String, active: bool) -> void:
	for agent_id in [player_id, resident_id]:
		if not _npcs.has(agent_id):
			continue
		var npc: Node = _npcs[agent_id]
		if npc.has_method("set_conversing"):
			npc.set_conversing(active)


func present_event(data: Dictionary) -> void:
	var agent_id := str(data.get("agent_id", ""))
	if not _npcs.has(agent_id):
		return
	var npc: Node = _npcs[agent_id]
	if npc.has_method("react"):
		npc.react(str(data.get("event", "")), str(data.get("item", "")))


func _place_cafe_bread() -> void:
	var cafe := get_node_or_null("POIs/cafe") as Node2D
	if cafe == null or cafe.get_node_or_null("Bread") != null:
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


const _NAMEPLATE_WIDTH := 56.0
const _NAMEPLATE_STEP := 16.0


func _stack_nameplates() -> void:
	var ids: Array[String] = []
	for agent_id in _npcs:
		ids.append(str(agent_id))
	var parent := {}
	for agent_id in ids:
		parent[agent_id] = agent_id
	for left in ids.size():
		for right in range(left + 1, ids.size()):
			var a := _npcs[ids[left]] as Node2D
			var b := _npcs[ids[right]] as Node2D
			if a == null or b == null:
				continue
			if a.global_position.distance_to(b.global_position) >= _NAMEPLATE_WIDTH:
				continue
			_union_nameplates(parent, ids[left], ids[right])
	var groups := {}
	for agent_id in ids:
		var root := _find_nameplate(parent, agent_id)
		if not groups.has(root):
			groups[root] = []
		(groups[root] as Array).append(agent_id)
	for root in groups:
		var members: Array = groups[root]
		members.sort_custom(func(a: String, b: String) -> bool:
			if a == _you:
				return true
			if b == _you:
				return false
			return a < b
		)
		for index in members.size():
			var npc: Node = _npcs[str(members[index])]
			if npc != null and npc.has_method("set_name_drop"):
				npc.set_name_drop(_NAMEPLATE_STEP * float(index))


func _find_nameplate(parent: Dictionary, agent_id: String) -> String:
	var root := str(parent.get(agent_id, agent_id))
	if root == agent_id:
		return agent_id
	root = _find_nameplate(parent, root)
	parent[agent_id] = root
	return root


func _union_nameplates(parent: Dictionary, left: String, right: String) -> void:
	var left_root := _find_nameplate(parent, left)
	var right_root := _find_nameplate(parent, right)
	if left_root != right_root:
		parent[right_root] = left_root


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
	_sync_place_label_visibility()
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
		sprite.modulate = _ui_color("poi_hover")
	_hover_label.text = _place_caption(poi_id)
	var anchor := _Rules.place_position(poi_id)
	_hover_label.position = anchor + Vector2(-60, -54)
	_hover_label.visible = true


func _place_caption(poi_id: String) -> String:
	if _show_content_ids:
		return "poi.%s" % poi_id
	return _Places.label(poi_id)


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
	label.position = _Rules.place_position(poi_id) + Vector2(-60, -68)
	label.size = Vector2(120, 16)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_map_label(label)
	add_child(label)
	return label


func _style_map_label(label: Label) -> void:
	label.theme_type_variation = "MapLabel"


func _sync_place_label_visibility() -> void:
	for poi_id in _place_labels:
		var label := _place_labels[poi_id] as CanvasItem
		if label != null:
			label.visible = str(poi_id) != _hover_id


func _ui_color(item: String) -> Color:
	return ThemeDB.get_project_theme().get_color(item, &"UI")


func _pointer_over_chrome() -> bool:
	var hud := get_parent().get_node_or_null("HUD")
	if hud != null and hud.has_method("blocks_pointer"):
		return bool(hud.blocks_pointer(get_viewport().get_mouse_position()))
	return false


func _make_destination_mark() -> Node2D:
	var mark := Node2D.new()
	mark.name = "Destination"
	mark.z_index = 25
	mark.visible = false
	var pin := Polygon2D.new()
	pin.color = _ui_color("destination")
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

