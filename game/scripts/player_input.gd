extends Node

const _FOOD := {"bread": true}
const _NAMES := {
	"bread": "麵包",
	"wood": "木材",
	"watering_can": "澆水壺",
}

@onready var _network: Node = $"../NetworkClient"
@onready var _world: Node2D = $"../World"
@onready var _hud: CanvasLayer = $"../HUD"

var _player_id := ""
var _location := ""
var _state := "idle"
var _front_id := ""
var _tools: Array = []
var _items: Array = []
var _selected := 0
var _others: Dictionary = {}
var _last_action := ""
var _last_item := ""
var _inspected := ""
var _talk_target := ""
var _talk_name := ""
var _talk_seq := 0


func _ready() -> void:
	_network.snapshot_received.connect(_on_snapshot)
	_network.agent_updated.connect(_on_agents)
	_network.intent_resolved.connect(_on_intent)
	_network.dialogue_received.connect(_on_dialogue)
	if _hud.has_signal("talk_submitted"):
		_hud.talk_submitted.connect(_on_talk_submitted)
	if _hud.has_signal("note_presented"):
		_hud.note_presented.connect(_on_present)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var click := event as InputEventMouseButton
		if click.pressed and click.button_index == MOUSE_BUTTON_LEFT:
			var audio := get_node_or_null("../GameAudio")
			if audio != null and audio.has_method("play_click"):
				audio.play_click()
			_click_move()
		return
	if event is InputEventKey:
		var key := event as InputEventKey
		if not key.pressed or key.echo:
			return
		match key.keycode:
			KEY_1:
				_use_tool(0)
			KEY_2:
				_use_tool(1)
			KEY_3:
				_use_tool(2)
			KEY_4:
				_use_selected()
			KEY_E:
				_pick_up()
			KEY_G:
				_give()
			KEY_Q:
				_cycle_selected()


func _on_snapshot(data: Dictionary) -> void:
	_player_id = str(data.get("you", ""))
	_others.clear()
	var agents: Variant = data.get("agents", [])
	if typeof(agents) == TYPE_ARRAY:
		for agent in agents:
			if typeof(agent) == TYPE_DICTIONARY:
				_remember(agent)
	_refresh_hotbar()


func _on_agents(data: Dictionary) -> void:
	var removed: Variant = data.get("removed", [])
	if typeof(removed) == TYPE_ARRAY:
		for agent_id in removed:
			var gone := str(agent_id)
			_others.erase(gone)
			if gone == _player_id:
				_player_id = ""
			if gone == _inspected:
				_inspected = ""
	var agents: Variant = data.get("agents", [])
	if typeof(agents) == TYPE_ARRAY:
		for agent in agents:
			if typeof(agent) == TYPE_DICTIONARY:
				_remember(agent)
	_refresh_hotbar()


func _on_intent(client_seq: int, ok: bool, reason: String) -> void:
	if reason == "superseded":
		return
	if client_seq == _talk_seq and _talk_seq != 0:
		if ok:
			if _hud.has_method("show_intent_reason"):
				_hud.show_intent_reason("")
			if _hud.has_method("start_waiting"):
				_hud.start_waiting(_talk_name)
		else:
			if _hud.has_method("stop_waiting"):
				_hud.stop_waiting()
			if _hud.has_method("show_intent_reason"):
				_hud.show_intent_reason(_reason_text(reason))
		_talk_seq = 0
		return
	if not _hud.has_method("show_intent_reason"):
		return
	if ok:
		_hud.show_intent_reason("")
		return
	_hud.show_intent_reason(_reason_text(reason))


func _reason_text(reason: String) -> String:
	match reason:
		"not_holding":
			return "手上沒有物品"
		"wrong_place":
			var tool_name := str(_NAMES.get(_last_item, ""))
			if tool_name.is_empty():
				return "這個地點不能用這個工具"
			return "這個地點不能用%s" % tool_name
		"nothing_here":
			if _last_action == "pick_up":
				return "這裡沒有麵包"
			return "這裡沒有那樣東西"
		"not_here":
			if _last_action == "give" or _last_action == "talk" or _last_action == "present_evidence":
				return "對方不在這裡"
			return "還沒走到那個地方"
		"not_food":
			return "這不能吃"
		"unknown_tool":
			return "沒有這個工具"
		"unknown_place":
			return "沒有這個地方"
		"unknown_agent":
			return "找不到對方"
		"npc_unavailable":
			return "他好像沒空理你。"
		"not_in_notes":
			return "筆記裡沒有這條"
		"too_long":
			return "這句話太長了。"
		"talk_limited":
			return "請等一下再問。"
		"rejected":
			return "這句話不能送出。"
		"empty":
			return "先寫一句話。"
		"busy":
			return "%s這會兒騰不出來。" % _talk_name
		"collapsed":
			return "對方現在起不來。"
		"rate_limited":
			return "太快了"
		"too_large":
			return "訊息太大"
		"players_disabled":
			return "玩家已關閉"
		"unsupported_target":
			return "不支援這個目標"
		"bad_intent":
			return "這個動作不對"
		"no_player":
			return "找不到玩家"
		_:
			return reason


func _remember(agent: Dictionary) -> void:
	var agent_id := str(agent.get("id", ""))
	if agent_id.is_empty():
		return
	var info: Dictionary = _others.get(agent_id, {})
	info["location"] = str(agent.get("location", ""))
	info["state"] = str(agent.get("state", ""))
	info["collapsed"] = bool(agent.get("collapsed", false))
	info["name"] = str(agent.get("name", agent_id))
	var needs: Variant = agent.get("needs", null)
	if typeof(needs) == TYPE_DICTIONARY:
		info["hunger"] = int(needs.get("hunger", 0))
		info["energy"] = int(needs.get("energy", 0))
		info["social"] = int(needs.get("social", 0))
	_others[agent_id] = info
	if agent_id == _inspected:
		_show_inspected()
	if agent_id != _player_id:
		return
	_location = str(agent.get("location", ""))
	_state = str(agent.get("state", ""))
	if agent.has("tools"):
		_tools = agent.get("tools", [])
	if agent.has("items"):
		_items = agent.get("items", [])
		if _selected >= _items.size():
			_selected = 0
	if info.has("hunger") and _hud.has_method("set_needs"):
		_hud.set_needs(int(info["hunger"]), int(info["energy"]), int(info["social"]))
	_refresh_confront_target()


func _refresh_hotbar() -> void:
	if not _hud.has_method("set_hotbar"):
		return
	var slots: Array = []
	for index in 3:
		var tool := ""
		if index < _tools.size():
			tool = str(_tools[index])
		if tool.is_empty():
			slots.append({"content_id": "", "count": 0, "selected": false})
		else:
			slots.append({
				"content_id": "tool.%s" % tool,
				"count": 1,
				"selected": false,
			})
	var selected := _selected_id()
	slots.append({
		"content_id": "item.%s" % selected if not selected.is_empty() else "",
		"count": _selected_count(),
		"selected": true,
	})
	_hud.set_hotbar(slots)


func _show_inspected() -> void:
	if _inspected.is_empty() or not _others.has(_inspected):
		return
	if not _hud.has_method("show_inspect"):
		return
	var info: Dictionary = _others[_inspected]
	if not info.has("hunger"):
		return
	_hud.show_inspect(
		str(info.get("name", _inspected)),
		int(info["hunger"]),
		int(info["energy"]),
		int(info["social"]),
	)


func _click_move() -> void:
	if not _world.has_method("poi_at"):
		return
	var mouse := get_viewport().get_mouse_position()
	var view := get_viewport().get_visible_rect().size
	if mouse.y >= view.y - 370.0 and mouse.x < 500.0:
		return
	if _hud.has_method("blocks_pointer") and _hud.blocks_pointer(mouse):
		return
	if mouse.y >= view.y - 150.0 and mouse.x < 660.0:
		return
	var world_at: Vector2 = _world.get_global_mouse_position()
	if _world.has_method("agent_at"):
		var hit := str(_world.agent_at(world_at))
		if not hit.is_empty():
			_inspected = hit
			_show_inspected()
			if hit != _player_id:
				var info: Dictionary = _others.get(hit, {})
				_talk_target = hit
				_talk_name = str(info.get("name", hit))
				if _hud.has_method("focus_resident"):
					_hud.focus_resident(hit, _talk_name)
			return
	var nearest := str(_world.poi_at(world_at))
	if nearest.is_empty():
		return
	var state := ""
	if _others.has(_player_id):
		state = str(_others[_player_id].get("state", ""))
	if nearest != _location or state == "walking":
		if _world.has_method("show_destination"):
			_world.show_destination(nearest)
	_send_intent({
		"action": "move_to",
		"target": {"type": "poi", "id": nearest},
	})


func _use_tool(index: int) -> void:
	if index >= _tools.size() or _location.is_empty():
		return
	_send_intent({
		"action": "use_tool",
		"target": {"type": "poi", "id": _location},
		"item": str(_tools[index]),
	})


func _use_selected() -> void:
	var item_id := _selected_id()
	if item_id.is_empty():
		_last_action = "eat"
		_show_local_reason("not_holding")
		return
	if not _FOOD.has(item_id):
		_last_action = "eat"
		_last_item = item_id
		_show_local_reason("not_food")
		return
	_send_intent({"action": "eat", "item": item_id})


func _pick_up() -> void:
	if _location.is_empty():
		return
	_send_intent({
		"action": "pick_up",
		"target": {"type": "poi", "id": _location},
		"item": "bread",
	})


func _give() -> void:
	var item_id := _selected_id()
	_last_action = "give"
	_last_item = item_id
	if item_id.is_empty():
		_show_local_reason("not_holding")
		return
	for agent_id in _others:
		if str(agent_id) == _player_id:
			continue
		var info: Dictionary = _others[agent_id]
		if str(info.get("location", "")) != _location:
			continue
		if str(info.get("state", "")) == "walking":
			continue
		_send_intent({
			"action": "give",
			"target": {"type": "agent", "id": str(agent_id)},
			"item": item_id,
		})
		return
	_show_local_reason("not_here")


func _cycle_selected() -> void:
	if _items.is_empty():
		return
	_selected = (_selected + 1) % _items.size()
	_refresh_hotbar()


func _send_intent(intent: Dictionary) -> void:
	_last_action = str(intent.get("action", ""))
	_last_item = str(intent.get("item", ""))
	var seq := int(_network.send_intent(intent))
	if _last_action == "talk":
		_talk_seq = seq


func _refresh_confront_target() -> void:
	if not _hud.has_method("set_confront_target"):
		return
	if _state == "walking" or _location.is_empty():
		_front_id = ""
		_hud.set_confront_target("")
		return
	for agent_id in _others:
		if str(agent_id) == _player_id:
			continue
		var info: Dictionary = _others[agent_id]
		if str(info.get("location", "")) != _location:
			continue
		if str(info.get("state", "")) == "walking":
			continue
		if bool(info.get("collapsed", false)):
			continue
		_front_id = str(agent_id)
		_hud.set_confront_target(_front_id)
		return
	_front_id = ""
	_hud.set_confront_target("")


func _on_present(fact_id: String) -> void:
	if _front_id.is_empty():
		_show_local_reason("not_here")
		return
	_send_intent({
		"action": "present_evidence",
		"target": {"type": "agent", "id": _front_id},
		"fact_id": fact_id,
	})


func _on_talk_submitted(text: String) -> void:
	if _talk_target.is_empty():
		_show_local_reason("unknown_agent")
		return
	if _hud.has_method("note_player_line"):
		_hud.note_player_line(text)
	_send_intent({
		"action": "talk",
		"target": {"type": "agent", "id": _talk_target},
		"text": text,
	})


func _on_dialogue(data: Dictionary) -> void:
	if _hud.has_method("show_private_reply"):
		_hud.show_private_reply(
			str(data.get("speaker_id", "")),
			str(data.get("reply", "")),
		)
	if data.has("notes") and _hud.has_method("set_notes"):
		var before := 0
		if _hud.has_method("note_count"):
			before = int(_hud.note_count())
		_hud.set_notes(data.get("notes"), data.get("note_ids", []))
		if _hud.has_method("note_count") and int(_hud.note_count()) > before:
			var audio := get_node_or_null("../GameAudio")
			if audio != null and audio.has_method("present_event"):
				audio.present_event({"event": "gave"})


func _show_local_reason(reason: String) -> void:
	if _hud.has_method("show_intent_reason"):
		_hud.show_intent_reason(_reason_text(reason))


func _selected_count() -> int:
	if _selected < 0 or _selected >= _items.size():
		return 0
	var stack: Variant = _items[_selected]
	if typeof(stack) != TYPE_DICTIONARY:
		return 0
	return int(stack.get("count", 0))


func _selected_id() -> String:
	if _selected < 0 or _selected >= _items.size():
		return ""
	var stack: Variant = _items[_selected]
	if typeof(stack) != TYPE_DICTIONARY:
		return ""
	return str(stack.get("id", ""))
