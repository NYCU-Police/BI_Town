extends CanvasLayer

@onready var _title_label: Label = %Title
@onready var _build_label: Label = %BuildLabel
@onready var _time_label: Label = %TimeLabel
@onready var _status_label: Label = %StatusLabel
@onready var _agents_label: Label = %AgentsLabel
@onready var _event_log: RichTextLabel = %EventLog

var _agent_names: Dictionary = {}
var _web_health_callback: Variant


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
	if OS.has_feature("web"):
		_request_health_web()
		return
	var http := HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(_on_health_completed)
	var err := http.request("http://127.0.0.1:8000/api/health")
	if err != OK:
		_show_unknown_identity()


func _request_health_web() -> void:
	# Relative /api/health follows the page origin (compose and production).
	# Keep the callback alive; Godot drops it if nothing references it.
	_web_health_callback = JavaScriptBridge.create_callback(_on_web_health)
	var window: Variant = JavaScriptBridge.get_interface("window")
	if window == null:
		_show_unknown_identity()
		return
	window.biTownOnHealth = _web_health_callback
	JavaScriptBridge.eval(
		"""
		fetch('/api/health').then(function (response) {
			if (!response.ok) {
				window.biTownOnHealth('');
				return;
			}
			response.text().then(function (text) {
				window.biTownOnHealth(text);
			}).catch(function () {
				window.biTownOnHealth('');
			});
		}).catch(function () {
			window.biTownOnHealth('');
		});
		""",
		true,
	)


func _on_web_health(args: Array) -> void:
	var text := ""
	if args.size() > 0 and args[0] != null:
		text = str(args[0])
	if text.is_empty():
		_show_unknown_identity()
		return
	_apply_health_text(text)


func _on_health_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		_show_unknown_identity()
		return
	_apply_health_text(body.get_string_from_utf8())


func _show_unknown_identity() -> void:
	_build_label.text = "commit unknown\ndeployed unknown"


func _apply_health_text(text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		_show_unknown_identity()
		return
	var data: Dictionary = parsed
	var service := str(data.get("service", "BI_Town"))
	var version := str(data.get("version", ""))
	if version.is_empty():
		_title_label.text = service
	else:
		_title_label.text = "%s v%s" % [service, version]
	var commit := str(data.get("git_commit", "unknown"))
	if commit.is_empty():
		commit = "unknown"
	var shown := commit
	if commit != "unknown" and commit.length() > 7:
		shown = commit.substr(0, 7)
	var deployed := str(data.get("deployed_at", "unknown"))
	if deployed.is_empty():
		deployed = "unknown"
	_build_label.text = "commit %s\ndeployed %s" % [shown, deployed]


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
