extends SceneTree

## Headless: connect, apply game_config, survive a backend restart, apply again.

var _world: Node
var _socket: WebSocketPeer
var _phase := 0
var _started := 0
var _retry_at := 0
var _first_count := 0


func _process(_delta: float) -> bool:
	if _started == 0:
		_started = Time.get_ticks_msec()
		var packed: PackedScene = load("res://scenes/world.tscn")
		_world = packed.instantiate()
		root.add_child(_world)
		_connect_now()
	if Time.get_ticks_msec() - _started > 20000:
		push_error("reconnect check timed out in phase %s" % _phase)
		quit(1)
		return true
	if _socket == null:
		if Time.get_ticks_msec() >= _retry_at:
			_connect_now()
		return false
	_socket.poll()
	match _socket.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			_world.call("set_link_up", true)
			while _socket.get_available_packet_count() > 0:
				var text := _socket.get_packet().get_string_from_utf8()
				_handle_text(text)
		WebSocketPeer.STATE_CLOSED:
			_world.call("set_link_up", false)
			_socket = null
			_retry_at = Time.get_ticks_msec() + 200
			if _phase == 1:
				print("backend socket closed; waiting to reconnect")
	return false


func _connect_now() -> void:
	_socket = WebSocketPeer.new()
	var err := _socket.connect_to_url("ws://127.0.0.1:8765/ws")
	if err != OK:
		push_error("connect failed: %s" % error_string(err))
		_socket = null
		_retry_at = Time.get_ticks_msec() + 200


func _handle_text(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var message: Dictionary = parsed
	if str(message.get("type", "")) != "game_config":
		return
	var data: Variant = message.get("data", {})
	if typeof(data) != TYPE_DICTIONARY:
		push_error("game_config data missing")
		quit(1)
		return
	if not bool(_world.call("apply_game_config", data)):
		push_error("apply_game_config rejected the payload")
		quit(1)
		return
	var count := _place_count()
	if _phase == 0:
		_first_count = count
		_phase = 1
		print("first config places=%s" % count)
		return
	if count != _first_count or count != (data as Dictionary).get("pois", []).size():
		push_error("place count changed across reconnect: %s -> %s" % [_first_count, count])
		quit(1)
		return
	_assert_play(data)
	print("reconnect config places=%s" % count)
	quit(0)


func _place_count() -> int:
	var pois := _world.get_node("POIs")
	var names := {}
	for child in pois.get_children():
		var place_name := str(child.name)
		names[place_name] = int(names.get(place_name, 0)) + 1
		if int(names[place_name]) != 1:
			push_error("duplicate place node %s" % place_name)
			quit(1)
	return names.size()


func _assert_play(data: Dictionary) -> void:
	var cafe := Vector2.ZERO
	var cafe_label := ""
	var pois: Variant = data.get("pois", [])
	for row in pois:
		if typeof(row) == TYPE_DICTIONARY and str(row.get("id", "")) == "cafe":
			cafe = Vector2(float(row.get("x", 0.0)), float(row.get("y", 0.0)))
			cafe_label = str(row.get("name", ""))
	if str(_world.call("poi_at", cafe)) != "cafe":
		push_error("cafe coordinate from game_config was not pickable")
		quit(1)
		return
	var found_label := false
	for child in _world.get_children():
		if child is Label and str((child as Label).text) == cafe_label:
			found_label = true
	if not found_label:
		push_error("cafe label was not taken from game_config")
		quit(1)
		return
	var npc_scene: PackedScene = load("res://scenes/npc.tscn")
	var npc: Node = npc_scene.instantiate()
	root.add_child(npc)
	var low := int(data.get("need_low", 0))
	npc.call("_read_needs", {"needs": {"hunger": low - 1}})
	npc.call("_refresh_status_emote")
	var emote := npc.get_node_or_null("Emote") as CanvasItem
	if emote == null or not emote.visible:
		push_error("hunger emote did not show below need_low")
		quit(1)
		return
	npc.call("_read_needs", {"needs": {"hunger": low}})
	npc.call("_refresh_status_emote")
	if emote.visible:
		push_error("hunger emote stayed up at need_low")
		quit(1)
