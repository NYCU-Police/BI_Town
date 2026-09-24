extends CanvasLayer

@onready var _title_label: Label = %Title
@onready var _build_label: Label = %BuildLabel
@onready var _time_label: Label = %TimeLabel
@onready var _status_label: Label = %StatusLabel
@onready var _agents_label: Label = %AgentsLabel
@onready var _event_log: RichTextLabel = %EventLog

var _agent_names: Dictionary = {}


func _ready() -> void:
	set_connection(false)
	_title_label.text = "BI_Town"
	_build_label.text = "commit —"
	_time_label.text = "Day — --:--"
	_agents_label.text = "Agents: 0"
	_request_health()


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


func _request_health() -> void:
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(_on_health_completed)
	var err := http.request(_health_url())
	if err != OK:
		push_error("GET /api/health failed to start: %s" % error_string(err))


func _on_health_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		push_error("GET /api/health failed (result=%s code=%s)" % [result, response_code])
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("health JSON parse failed")
		return
	var data: Dictionary = parsed
	var service := str(data.get("service", "BI_Town"))
	var version := str(data.get("version", ""))
	if version.is_empty():
		_title_label.text = service
	else:
		_title_label.text = "%s v%s" % [service, version]
	var commit := str(data.get("git_commit", "unknown"))
	var shown := commit
	if commit != "unknown" and commit.length() > 7:
		shown = commit.substr(0, 7)
	var deployed := str(data.get("deployed_at", "unknown"))
	_build_label.text = "commit %s\ndeployed %s" % [shown, deployed]


func _health_url() -> String:
	if not OS.has_feature("web"):
		return "http://127.0.0.1:8000/api/health"

	var override_url := _websocket_override_from_query()
	if not override_url.is_empty():
		return _http_health_from_websocket(override_url)

	var location: Variant = JavaScriptBridge.get_interface("location")
	if location == null:
		push_error("JavaScriptBridge location unavailable; using desktop health URL")
		return "http://127.0.0.1:8000/api/health"
	return "%s//%s/api/health" % [str(location.protocol), str(location.host)]


func _websocket_override_from_query() -> String:
	var raw: Variant = JavaScriptBridge.eval(
		"decodeURIComponent(new URLSearchParams(window.location.search).get('ws') || '')"
	)
	if raw == null:
		return ""
	return str(raw).strip_edges()


func _http_health_from_websocket(websocket_url: String) -> String:
	var http_url := websocket_url.replace("wss://", "https://").replace("ws://", "http://")
	var path_at := http_url.find("/ws")
	if path_at >= 0:
		http_url = http_url.substr(0, path_at)
	return http_url.trim_suffix("/") + "/api/health"


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
