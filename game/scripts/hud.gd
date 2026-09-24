extends CanvasLayer

const _MATCH_COLOR := Color(0.65, 0.67, 0.64)
const _MISMATCH_COLOR := Color(0.96, 0.62, 0.18)

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
	_render_identity(_read_local_frontend_commit(), "", "", false)
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
		_render_identity(_read_local_frontend_commit(), "unknown", "unknown", true)


func _request_health_web() -> void:
	# Loose /build_info.json is the export stamp. /api/health is the backend.
	# Keep the callback alive; Godot drops it if nothing references it.
	_web_health_callback = JavaScriptBridge.create_callback(_on_web_health)
	var window: Variant = JavaScriptBridge.get_interface("window")
	if window == null:
		_render_identity("unknown", "unknown", "unknown", true)
		return
	window.biTownOnHealth = _web_health_callback
	JavaScriptBridge.eval(
		"""
		function biTownFinish(infoText, healthText) {
			window.biTownOnHealth(infoText || '', healthText || '');
		}
		fetch('/build_info.json').then(function (response) {
			if (!response.ok) {
				return '';
			}
			return response.text();
		}).catch(function () {
			return '';
		}).then(function (infoText) {
			fetch('/api/health').then(function (response) {
				if (!response.ok) {
					biTownFinish(infoText, '');
					return;
				}
				response.text().then(function (healthText) {
					biTownFinish(infoText, healthText);
				}).catch(function () {
					biTownFinish(infoText, '');
				});
			}).catch(function () {
				biTownFinish(infoText, '');
			});
		});
		""",
		true,
	)


func _on_web_health(args: Array) -> void:
	var info_text := ""
	var health_text := ""
	if args.size() > 0 and args[0] != null:
		info_text = str(args[0])
	if args.size() > 1 and args[1] != null:
		health_text = str(args[1])
	var frontend := _commit_from_build_info(info_text)
	if health_text.is_empty():
		_render_identity(frontend, "unknown", "unknown", true)
		return
	_apply_health_text(frontend, health_text)


func _on_health_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	var frontend := _read_local_frontend_commit()
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		_render_identity(frontend, "unknown", "unknown", true)
		return
	_apply_health_text(frontend, body.get_string_from_utf8())


func _read_local_frontend_commit() -> String:
	if not FileAccess.file_exists("res://build_info.json"):
		return "unknown"
	return _commit_from_build_info(FileAccess.get_file_as_string("res://build_info.json"))


func _commit_from_build_info(text: String) -> String:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return "unknown"
	var commit := str(parsed.get("commit", "unknown")).strip_edges()
	if commit.is_empty():
		return "unknown"
	return commit


func _apply_health_text(frontend: String, text: String) -> void:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		_render_identity(frontend, "unknown", "unknown", true)
		return
	var data: Dictionary = parsed
	var service := str(data.get("service", "BI_Town"))
	var version := str(data.get("version", ""))
	if version.is_empty():
		_title_label.text = service
	else:
		_title_label.text = "%s v%s" % [service, version]
	var backend := str(data.get("git_commit", "unknown")).strip_edges()
	if backend.is_empty():
		backend = "unknown"
	var deployed := str(data.get("deployed_at", "unknown")).strip_edges()
	if deployed.is_empty():
		deployed = "unknown"
	_render_identity(frontend, backend, deployed, true)


func _render_identity(frontend: String, backend: String, deployed: String, settled: bool) -> void:
	if frontend.is_empty():
		frontend = "unknown"
	var backend_text := backend if not backend.is_empty() else "…"
	var deployed_text := deployed if not deployed.is_empty() else "…"
	_build_label.text = "frontend %s\nbackend %s\ndeployed %s" % [
		_short_commit(frontend),
		_short_commit(backend_text),
		deployed_text,
	]
	var color := _MATCH_COLOR
	if settled and frontend != backend:
		color = _MISMATCH_COLOR
	_build_label.add_theme_color_override("font_color", color)


func _short_commit(commit: String) -> String:
	if commit != "unknown" and commit != "…" and commit.length() > 7:
		return commit.substr(0, 7)
	return commit


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
