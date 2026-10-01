extends SceneTree

## Headless check: applying game_config twice must not duplicate place nodes.

var _done := false


func _process(_delta: float) -> bool:
	if not _done:
		_done = true
		_run()
	return false


func _run() -> void:
	var packed: PackedScene = load("res://scenes/world.tscn")
	if packed == null:
		push_error("world scene missing")
		quit(1)
		return
	var world: Node = packed.instantiate()
	root.add_child(world)
	var config := {
		"version": 1,
		"pois": [
			{"id": "plaza", "name": "Plaza", "x": 280.0, "y": 192.0},
			{"id": "cafe", "name": "Cafe", "x": 392.0, "y": 96.0},
		],
		"poi_pick_radius": 56.0,
		"agent_pick_radius": 36.0,
		"need_low": 30,
		"eat_restore": 35,
		"items": [{"id": "bread", "name": "Bread", "food": true}],
	}
	world.call("set_link_up", true)
	if not bool(world.call("apply_game_config", config)):
		push_error("first apply_game_config failed")
		quit(1)
		return
	if not bool(world.call("apply_game_config", config)):
		push_error("second apply_game_config failed")
		quit(1)
		return
	var pois := world.get_node("POIs")
	var names := {}
	for child in pois.get_children():
		names[str(child.name)] = int(names.get(str(child.name), 0)) + 1
	if int(names.get("plaza", 0)) != 1 or int(names.get("cafe", 0)) != 1 or names.size() != 2:
		push_error("place nodes after two applies: %s" % str(names))
		quit(1)
		return
	var breads := 0
	for child in pois.get_node("cafe").get_children():
		if str(child.name) == "Bread":
			breads += 1
	if breads != 1:
		push_error("bread nodes: %s" % breads)
		quit(1)
		return
	var labels := 0
	for child in world.get_children():
		if child is Label and str(child.name) != "PoiHover" and str(child.name) != "PlazaNotice":
			labels += 1
	if labels != 2:
		push_error("place labels: %s" % labels)
		quit(1)
		return
	if not bool(world.call("playable")):
		push_error("expected clicks to be enabled after config")
		quit(1)
		return
	var camera := world.get_node("Camera") as Camera2D
	if camera == null or camera.position == Vector2.ZERO:
		push_error("camera was not framed on the plaza from game_config")
		quit(1)
		return
	print("game_config upsert ok")
	quit(0)
