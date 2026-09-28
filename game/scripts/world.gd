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

@export var npc_scene: PackedScene

var _npcs: Dictionary = {}


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


func apply_snapshot(data: Dictionary) -> void:
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("world_snapshot.agents is not an array")
		return
	for agent in agents:
		if typeof(agent) == TYPE_DICTIONARY:
			_upsert_npc(agent, true)
	_separate_overlaps(true)


func apply_agent_update(data: Dictionary) -> void:
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("agent_update.agents is not an array")
		return
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
