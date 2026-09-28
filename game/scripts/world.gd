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

const PLACE_NAMES := {
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

## Building labels are centered on the roof and sit on its top edge.
## South-row roofs are the bottom row, so those labels stay on the building.
const _LABEL_OFFSET := {
	"mina_home": Vector2(-72, -96),
	"alex_home": Vector2(-72, -96),
	"rin_home": Vector2(-72, -96),
	"cafe": Vector2(-72, -96),
	"store": Vector2(-72, -96),
	"office": Vector2(-72, 30),
	"library": Vector2(-72, 30),
	"plaza": Vector2(-72, -28),
	"park": Vector2(-128, -52),
}

@export var npc_scene: PackedScene

var _npcs: Dictionary = {}


func _ready() -> void:
	texture_filter = TEXTURE_FILTER_NEAREST
	var pois_root := get_node_or_null("POIs")
	if pois_root == null:
		push_error("World is missing the POIs node")
		return
	for child in pois_root.get_children():
		child.queue_free()
	for poi_id in POIS:
		var node := Node2D.new()
		node.name = poi_id
		node.position = POIS[poi_id]
		var label := Label.new()
		label.text = str(PLACE_NAMES[poi_id])
		label.position = _LABEL_OFFSET[poi_id]
		label.size = Vector2(144, 16)
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		label.add_theme_color_override("font_color", Color.WHITE)
		label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 1))
		label.add_theme_constant_override("outline_size", 4)
		label.add_theme_font_size_override("font_size", 12)
		node.add_child(label)
		pois_root.add_child(node)


func apply_snapshot(data: Dictionary) -> void:
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
	if npc.has_method("set_stand_offset"):
		npc.set_stand_offset(Vector2.ZERO, snap)
