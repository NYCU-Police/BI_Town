extends Node2D

## Must match backend/app/simulation/poi.py
const POIS := {
	"home": Vector2(100, 100),
	"cafe": Vector2(400, 250),
	"office": Vector2(700, 150),
	"park": Vector2(500, 500),
}

@export var npc_scene: PackedScene

var _npcs: Dictionary = {}


func _ready() -> void:
	var node_names := {
		"home": "Home",
		"cafe": "Cafe",
		"office": "Office",
		"park": "Park",
	}
	for poi_id in POIS:
		var node := get_node_or_null("POIs/%s" % node_names[poi_id])
		if node == null:
			push_error("Missing POI node for %s" % poi_id)
			continue
		if node.position != POIS[poi_id]:
			push_error("POI %s is at %s, backend expects %s" % [poi_id, node.position, POIS[poi_id]])


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
		npc.set_stand_offset(_stand_offset_for(agent), snap)


## Display-only. Server coordinates stay on the POI. Idle residents stand
## on the ground in front of the door tiles (town_map bottom row, columns 1–2).
func _stand_offset_for(agent: Dictionary) -> Vector2:
	if str(agent.get("state", "")) != "idle":
		return Vector2.ZERO
	var pos_v: Variant = agent.get("position", {})
	if typeof(pos_v) != TYPE_DICTIONARY:
		return Vector2.ZERO
	var coords: Dictionary = pos_v
	var pos := Vector2(float(coords.get("x", 0.0)), float(coords.get("y", 0.0)))
	for poi in POIS.values():
		if pos.distance_to(poi) <= 1.0:
			return _door_delta(poi)
	return Vector2.ZERO


func _door_delta(poi: Vector2) -> Vector2:
	var origin_x := int(round(poi.x / 16.0)) - 2
	var origin_y := int(round(poi.y / 16.0)) - 2
	var door_x := float(origin_x + 2) * 16.0
	# Sprite is 48px tall. Keep the body on the ground in front of the door,
	# with only the top of the head overlapping the doorway.
	var feet_y := float(origin_y + 4) * 16.0 + 42.0
	return Vector2(door_x - poi.x, feet_y - poi.y)
