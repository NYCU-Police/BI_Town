extends CanvasLayer

@onready var _time_label: Label = %TimeLabel
@onready var _status_label: Label = %StatusLabel
@onready var _agents_label: Label = %AgentsLabel
@onready var _event_log: RichTextLabel = %EventLog

var _agent_names: Dictionary = {}


func _ready() -> void:
	set_connection(false)
	_time_label.text = "Day — --:--"
	_agents_label.text = "Agents: 0"


func apply_snapshot(data: Dictionary) -> void:
	_set_clock(data)
	_agent_names.clear()
	var agents: Variant = data.get("agents", [])
	if typeof(agents) == TYPE_ARRAY:
		for agent in agents:
			if typeof(agent) == TYPE_DICTIONARY:
				_remember_agent(agent)
		_agents_label.text = "Agents: %s" % agents.size()
	else:
		push_error("world_snapshot.agents is not an array")

	if _event_log.has_method("clear_events"):
		_event_log.clear_events()
	var events: Variant = data.get("events", [])
	if typeof(events) != TYPE_ARRAY:
		push_error("world_snapshot.events is not an array")
		return
	for i in range(events.size() - 1, -1, -1):
		if typeof(events[i]) == TYPE_DICTIONARY:
			_append_event(events[i])


func apply_agent_update(data: Dictionary) -> void:
	_set_clock(data)
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("agent_update.agents is not an array")
		return
	for agent in agents:
		if typeof(agent) == TYPE_DICTIONARY:
			_remember_agent(agent)
	if not _agent_names.is_empty():
		_agents_label.text = "Agents: %s" % _agent_names.size()


func apply_event(data: Dictionary) -> void:
	_append_event(data)


func set_connection(online: bool) -> void:
	if online:
		_status_label.text = "Server  ● Online"
		_status_label.add_theme_color_override("font_color", Color(0.35, 0.85, 0.45))
	else:
		_status_label.text = "Server  ● Offline"
		_status_label.add_theme_color_override("font_color", Color(0.90, 0.32, 0.32))


func _set_clock(data: Dictionary) -> void:
	if data.has("day") and data.has("time"):
		_time_label.text = "Day %s — %s" % [data["day"], data["time"]]


func _remember_agent(agent: Dictionary) -> void:
	var agent_id := str(agent.get("id", ""))
	if agent_id.is_empty():
		return
	_agent_names[agent_id] = str(agent.get("name", agent_id))


func _append_event(data: Dictionary) -> void:
	if not _event_log.has_method("add_event"):
		push_error("EventLog is missing add_event()")
		return
	_event_log.add_event(_format_event(data))


func _format_event(data: Dictionary) -> String:
	var timestamp := str(data.get("timestamp", "--:--"))
	var agent_id := str(data.get("agent_id", ""))
	var agent_name := str(_agent_names.get(agent_id, agent_id.capitalize()))
	var action := str(data.get("event", ""))
	var location := str(data.get("location", "")).capitalize()
	return "%s %s %s %s" % [timestamp, agent_name, action, location]
