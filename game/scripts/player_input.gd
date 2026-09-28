extends Node

const _CLICK_RADIUS := 56.0
const _FOOD := {"bread": true}
const _REASONS := {
	"not_here": "還不在同一個地方",
	"nothing_here": "這裡沒有那樣東西",
	"not_holding": "手上沒有",
	"not_food": "這不能吃",
	"rate_limited": "太快了",
	"too_large": "訊息太大",
	"wrong_place": "這裡用不了",
	"unknown_tool": "沒有這個工具",
	"unknown_place": "沒有這個地方",
	"unknown_agent": "找不到對方",
	"players_disabled": "玩家已關閉",
	"unsupported_target": "不支援這個目標",
	"bad_intent": "這個動作不對",
}

@onready var _network: Node = $"../NetworkClient"
@onready var _world: Node2D = $"../World"
@onready var _hud: CanvasLayer = $"../HUD"

var _player_id := ""
var _location := ""
var _tools: Array = []
var _items: Array = []
var _selected := 0
var _others: Dictionary = {}


func _ready() -> void:
	_network.snapshot_received.connect(_on_snapshot)
	_network.agent_updated.connect(_on_agents)
	_network.intent_resolved.connect(_on_intent)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var click := event as InputEventMouseButton
		if click.pressed and click.button_index == MOUSE_BUTTON_LEFT:
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
	var agents: Variant = data.get("agents", [])
	if typeof(agents) == TYPE_ARRAY:
		for agent in agents:
			if typeof(agent) == TYPE_DICTIONARY:
				_remember(agent)
	_refresh_hotbar()


func _on_intent(_client_seq: int, ok: bool, reason: String) -> void:
	if ok or not _hud.has_method("show_intent_reason"):
		if ok and _hud.has_method("show_intent_reason"):
			_hud.show_intent_reason("")
		return
	var text := str(_REASONS.get(reason, reason))
	_hud.show_intent_reason(text)


func _remember(agent: Dictionary) -> void:
	var agent_id := str(agent.get("id", ""))
	if agent_id.is_empty():
		return
	_others[agent_id] = {
		"location": str(agent.get("location", "")),
		"state": str(agent.get("state", "")),
	}
	if agent_id != _player_id:
		return
	_location = str(agent.get("location", ""))
	if agent.has("tools"):
		_tools = agent.get("tools", [])
	if agent.has("items"):
		_items = agent.get("items", [])
		if _selected >= _items.size():
			_selected = 0
	var needs: Variant = agent.get("needs", null)
	if typeof(needs) == TYPE_DICTIONARY and _hud.has_method("set_needs"):
		_hud.set_needs(
			int(needs.get("hunger", 0)),
			int(needs.get("energy", 0)),
			int(needs.get("social", 0)),
		)


func _refresh_hotbar() -> void:
	if not _hud.has_method("set_hotbar"):
		return
	var content_ids: Array[String] = []
	for index in 3:
		var tool := ""
		if index < _tools.size():
			tool = str(_tools[index])
		content_ids.append("tool.%s" % tool if not tool.is_empty() else "")
	var selected := _selected_id()
	content_ids.append("item.%s" % selected if not selected.is_empty() else "")
	_hud.set_hotbar(content_ids)


func _click_move() -> void:
	var pois := _world.get_node_or_null("POIs")
	if pois == null:
		return
	var where := _world.get_global_mouse_position()
	var nearest := ""
	var best := _CLICK_RADIUS
	for child in pois.get_children():
		var marker := child as Node2D
		if marker == null:
			continue
		var distance := where.distance_to(marker.global_position)
		if distance <= best:
			best = distance
			nearest = str(marker.name)
	if nearest.is_empty():
		return
	_network.send_intent({
		"action": "move_to",
		"target": {"type": "poi", "id": nearest},
	})


func _use_tool(index: int) -> void:
	if index >= _tools.size() or _location.is_empty():
		return
	_network.send_intent({
		"action": "use_tool",
		"target": {"type": "poi", "id": _location},
		"item": str(_tools[index]),
	})


func _use_selected() -> void:
	var item_id := _selected_id()
	if item_id.is_empty():
		return
	if not _FOOD.has(item_id):
		if _hud.has_method("show_intent_reason"):
			_hud.show_intent_reason(str(_REASONS["not_food"]))
		return
	_network.send_intent({"action": "eat", "item": item_id})


func _pick_up() -> void:
	if _location.is_empty():
		return
	_network.send_intent({
		"action": "pick_up",
		"target": {"type": "poi", "id": _location},
		"item": "bread",
	})


func _give() -> void:
	var item_id := _selected_id()
	if item_id.is_empty():
		return
	for agent_id in _others:
		if str(agent_id) == _player_id:
			continue
		var info: Dictionary = _others[agent_id]
		if str(info.get("location", "")) != _location:
			continue
		if str(info.get("state", "")) == "walking":
			continue
		_network.send_intent({
			"action": "give",
			"target": {"type": "agent", "id": str(agent_id)},
			"item": item_id,
		})
		return
	if _hud.has_method("show_intent_reason"):
		_hud.show_intent_reason(str(_REASONS["not_here"]))


func _cycle_selected() -> void:
	if _items.is_empty():
		return
	_selected = (_selected + 1) % _items.size()
	_refresh_hotbar()


func _selected_id() -> String:
	if _selected < 0 or _selected >= _items.size():
		return ""
	var stack: Variant = _items[_selected]
	if typeof(stack) != TYPE_DICTIONARY:
		return ""
	return str(stack.get("id", ""))
