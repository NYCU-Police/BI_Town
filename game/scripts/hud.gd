extends CanvasLayer

signal talk_submitted(text: String)
signal note_presented(fact_id: String)
signal dialogue_target_changed

const _Places := preload("res://scripts/place_names.gd")
## Same line as the server's hungry / exhausted / lonely marks.
const _LOW_NEED := 30
const _HINT := "點地點移動　1–3 工具　4 使用　E 撿　G 給予　Q 切換　N 筆記"
const _IDLE_PLACEHOLDER := "點一位居民，再打字　N 筆記"
const _DIALOGUE_RECT := Rect2(16, 496, 848, 144)
const _NOTEBOOK_RECT := Rect2(904, 48, 360, 392)
const _LOG_RECT := Rect2(944, 48, 320, 280)
const _INPUT_RECT := Rect2(26, 600, 828, 32)
const _LOG_BUTTON_RECT := Rect2(880, 496, 72, 24)
const _MOVE_EVENTS := ["left", "entered", "activity"]
const _ITEM_EVENTS := ["ate", "gave", "picked_up"]

@onready var _build_label: Label = %BuildLabel
@onready var _time_label: Label = %TimeLabel
@onready var _status_label: Label = %StatusLabel
@onready var _event_log: RichTextLabel = %EventLog
@onready var _hunger_label: Label = %HungerLabel
@onready var _energy_label: Label = %EnergyLabel
@onready var _social_label: Label = %SocialLabel
@onready var _intent_label: Label = %IntentLabel
@onready var _mute_button: Button = %MuteButton
@onready var _log_button: Button = %LogButton
@onready var _move_button: Button = %MoveButton
@onready var _log_drawer: Panel = $LogDrawer
@onready var _bottom_bar: Panel = $BottomBar
@onready var _bottom_box: VBoxContainer = $BottomBar/VBox

var _slots: Array[Panel] = []

var _agent_names: Dictionary = {}
var _web_health_callback: Variant
var _name_hex: Dictionary = {}
var _said_hex := ""
var _thought_hex := ""
var _move_hex := ""
var _dialogue: Panel
var _dialogue_name: Label
var _talk_hunger: Label
var _talk_energy: Label
var _talk_social: Label
var _dialogue_log: RichTextLabel
var _dialogue_status: Label
var _dialogue_line: LineEdit
var _talk_lines: PackedStringArray = PackedStringArray()
var _notebook: Panel
var _note_box: VBoxContainer
var _note_texts: PackedStringArray = PackedStringArray()
var _note_fact_ids: PackedStringArray = PackedStringArray()
var _confront_target := ""
var _dialogue_speaker := ""
var _waiting := false
var _wait_name := ""
var _dot_phase := 0
var _dot_accum := 0.0
var _seen_name := ""
var _seen_hunger := 0
var _seen_energy := 0
var _seen_social := 0
var _seen_ready := false


func _ready() -> void:
	_slots = [%Slot1, %Slot2, %Slot3, %Slot4]
	_cache_theme_colors()
	_event_log.meta_clicked.connect(_on_log_meta)
	_mute_button.pressed.connect(_toggle_mute)
	_log_button.pressed.connect(_toggle_event_log)
	_move_button.pressed.connect(_toggle_movement)
	_bottom_box.minimum_size_changed.connect(_fit_bottom_bar)
	get_viewport().size_changed.connect(_layout_chrome)
	set_connection(false)
	_render_identity(_read_local_frontend_commit(), "", "", false)
	_time_label.text = "Day —  --:--"
	_intent_label.text = ""
	_intent_label.visible = false
	set_hotbar([
		{"content_id": "", "count": 0, "selected": false},
		{"content_id": "", "count": 0, "selected": false},
		{"content_id": "", "count": 0, "selected": false},
		{"content_id": "", "count": 0, "selected": true},
	])
	_request_health()
	_build_dialogue()
	_build_notebook()
	_layout_chrome()


func apply_snapshot(data: Dictionary) -> void:
	_set_clock(data)
	_agent_names.clear()
	var agents: Variant = data.get("agents", [])
	if typeof(agents) == TYPE_ARRAY:
		for agent in agents:
			if typeof(agent) == TYPE_DICTIONARY:
				_remember_agent(agent)
	else:
		push_error("world_snapshot.agents is not an array")

	_restore_dialogue(data.get("dialogue_history", []))
	set_notes(data.get("notes", []), data.get("note_ids", []))
	if _event_log.has_method("clear_events"):
		_event_log.clear_events()
	var events: Variant = data.get("events", [])
	if typeof(events) != TYPE_ARRAY:
		push_error("world_snapshot.events is not an array")
		return
	for event in events:
		if typeof(event) == TYPE_DICTIONARY:
			_append_event(event)


func apply_agent_update(data: Dictionary) -> void:
	_set_clock(data)
	var agents: Variant = data.get("agents", [])
	if typeof(agents) != TYPE_ARRAY:
		push_error("agent_update.agents is not an array")
		return
	var removed: Variant = data.get("removed", [])
	if typeof(removed) == TYPE_ARRAY:
		for agent_id in removed:
			_agent_names.erase(str(agent_id))
	for agent in agents:
		if typeof(agent) == TYPE_DICTIONARY:
			_remember_agent(agent)


func apply_event(data: Dictionary) -> void:
	_append_event(data)


func set_connection(online: bool) -> void:
	if online:
		_status_label.text = "● 已連線"
		_status_label.theme_type_variation = "Accent"
	else:
		_status_label.text = "● 離線"
		_status_label.theme_type_variation = "Warn"


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
	var trimmed := text.strip_edges()
	if not trimmed.begins_with("{"):
		return "unknown"
	var parsed: Variant = JSON.parse_string(trimmed)
	if typeof(parsed) != TYPE_DICTIONARY:
		return "unknown"
	var commit := str(parsed.get("commit", "unknown")).strip_edges()
	if commit.is_empty():
		return "unknown"
	return commit


func _apply_health_text(frontend: String, text: String) -> void:
	var trimmed := text.strip_edges()
	if not trimmed.begins_with("{"):
		_render_identity(frontend, "unknown", "unknown", true)
		return
	var parsed: Variant = JSON.parse_string(trimmed)
	if typeof(parsed) != TYPE_DICTIONARY:
		_render_identity(frontend, "unknown", "unknown", true)
		return
	var data: Dictionary = parsed
	var backend := str(data.get("git_commit", "unknown")).strip_edges()
	if backend.is_empty():
		backend = "unknown"
	var deployed := str(data.get("deployed_at", "unknown")).strip_edges()
	if deployed.is_empty():
		deployed = "unknown"
	_render_identity(frontend, backend, deployed, true)


func _render_identity(frontend: String, backend: String, _deployed: String, settled: bool) -> void:
	if frontend.is_empty():
		frontend = "unknown"
	var backend_text := backend if not backend.is_empty() else "…"
	var mismatch := (
		settled
		and frontend != "unknown"
		and backend_text != "unknown"
		and backend_text != "…"
		and frontend != backend_text
	)
	_build_label.visible = mismatch
	if not mismatch:
		return
	_build_label.theme_type_variation = "Accent"
	_build_label.text = "%s / %s" % [_short_commit(frontend), _short_commit(backend_text)]


func _short_commit(commit: String) -> String:
	if commit != "unknown" and commit != "…" and commit.length() > 7:
		return commit.substr(0, 7)
	return commit


func set_hotbar(slots: Array) -> void:
	for index in _slots.size():
		var slot: Panel = _slots[index]
		var content_id := ""
		var count := 0
		var selected := false
		if index < slots.size() and typeof(slots[index]) == TYPE_DICTIONARY:
			var info: Dictionary = slots[index]
			content_id = str(info.get("content_id", ""))
			count = int(info.get("count", 0))
			selected = bool(info.get("selected", false))
		slot.theme_type_variation = "SlotSelected" if selected else "Slot"
		var number := slot.get_node("Number") as Label
		number.text = str(index + 1)
		var count_label := slot.get_node("Count") as Label
		count_label.text = str(count) if count > 0 else ""
		var host := slot.get_node("IconHost") as Control
		if content_id.is_empty():
			_clear_slot_icon(host)
		else:
			VisualBinder.apply_icon(host, content_id)


func _toggle_mute() -> void:
	var audio := get_parent().get_node_or_null("GameAudio")
	if audio == null or not audio.has_method("set_muted"):
		return
	var muted := true
	if audio.has_method("is_muted"):
		muted = not bool(audio.is_muted())
	audio.set_muted(muted)
	if _mute_button != null:
		_mute_button.text = "靜音" if muted else "聲音"


func _clear_slot_icon(host: Control) -> void:
	var icon := host.get_node_or_null("Icon")
	if icon != null:
		icon.queue_free()
	var fallback := host.get_node_or_null("Fallback")
	if fallback != null:
		fallback.queue_free()


func set_needs(hunger: int, energy: int, social: int) -> void:
	_paint_need(_hunger_label, "飢餓", hunger)
	_paint_need(_energy_label, "體力", energy)
	_paint_need(_social_label, "社交", social)


func show_intent_reason(reason: String) -> void:
	_intent_label.text = reason
	_intent_label.visible = not reason.is_empty()


func show_inspect(agent_name: String, hunger: int, energy: int, social: int) -> void:
	_seen_name = agent_name
	_seen_hunger = hunger
	_seen_energy = energy
	_seen_social = social
	_seen_ready = true
	_apply_talk_needs()


func _paint_need(label: Label, title: String, value: int) -> void:
	label.text = "%s %d" % [title, value]
	label.theme_type_variation = "NeedLow" if value < _LOW_NEED else ""


func _apply_talk_needs() -> void:
	if _talk_hunger == null:
		return
	var matched := _seen_ready and _dialogue_name != null and _dialogue_name.text == _seen_name
	_talk_hunger.visible = matched
	_talk_energy.visible = matched
	_talk_social.visible = matched
	if not matched:
		return
	_paint_need(_talk_hunger, "飢餓", _seen_hunger)
	_paint_need(_talk_energy, "體力", _seen_energy)
	_paint_need(_talk_social, "社交", _seen_social)


func _set_clock(data: Dictionary) -> void:
	if data.has("day") and data.has("time"):
		_time_label.text = "Day %d  %s" % [int(data["day"]), data["time"]]


func _remember_agent(agent: Dictionary) -> void:
	var agent_id := str(agent.get("id", ""))
	if agent_id.is_empty():
		return
	_agent_names[agent_id] = str(agent.get("name", agent_id))


func _append_event(data: Dictionary) -> void:
	var action := str(data.get("event", ""))
	if action == "produced" or action == "conversing_ended":
		return
	if not _event_log.has_method("add_event"):
		push_error("EventLog is missing add_event()")
		return
	_event_log.add_event(_format_event(data), _event_category(action))


func _event_category(action: String) -> String:
	if action in _ITEM_EVENTS:
		return "item"
	if action in _MOVE_EVENTS:
		return "move"
	return "talk"


func _escape_bbcode(line: String) -> String:
	return line.replace("[", "[lb]")


func _colored_name(agent_id: String) -> String:
	var agent_name := str(_agent_names.get(agent_id, agent_id.capitalize()))
	var color := str(_name_hex.get(agent_id, _said_hex))
	return "[url=%s][color=%s]%s[/color][/url]" % [
		agent_id,
		color,
		_escape_bbcode(agent_name),
	]


func _place_label(poi_id: String) -> String:
	return _Places.label(poi_id)


func _on_log_meta(meta: Variant) -> void:
	get_tree().call_group("town_camera", "focus_agent", str(meta))


func _tone(text: String, color: String) -> String:
	return "[color=%s]%s[/color]" % [color, _escape_bbcode(text)]


const _EVENT_TEMPLATES := {
	"left": "{time} {name} 離開 {place}",
	"entered": "{time} {name} 抵達 {place}",
	"activity": "{time} {name} 在{place} {task}",
	"ate": "{time} {name} 吃了 {item}",
	"gave": "{time} {name} 把 {item} 給了 {target}",
	"picked_up": "{time} {name} 撿起 {item}",
	"produced": "{time} {name} 做出 {item}",
	"said": "{time} {name}{arrow}\n{quote}",
	"thought": "{time} {name}（想）\n{quote}",
	"conversing": "{time} {name} 正在和 {target} 說話",
}
const _ITEM_NAMES := {
	"bread": "麵包",
	"wood": "木材",
	"watering_can": "澆水壺",
}


func _format_event(data: Dictionary) -> String:
	var action := str(data.get("event", ""))
	var template := str(_EVENT_TEMPLATES.get(action, "{time} {name} {action}"))
	var dim := action == "thought" or action in _MOVE_EVENTS
	var color := _thought_hex if action == "thought" else (_move_hex if action in _MOVE_EVENTS else _said_hex)
	var target_id := str(data.get("target_agent_id", ""))
	var arrow := ""
	if action == "said" and not target_id.is_empty():
		arrow = " %s %s" % [_tone("→", _said_hex), _colored_name(target_id)]
	var spoken := str(data.get("content", ""))
	var quote := "「%s」" % spoken if action == "said" else spoken
	var fields := {
		"time": _tone(str(data.get("timestamp", "--:--")), color),
		"name": _colored_name(str(data.get("agent_id", ""))),
		"place": _tone(_place_label(str(data.get("location", ""))), color),
		"task": _tone(str(data.get("content", "")), color),
		"item": _tone(_item_label(str(data.get("item", ""))), color),
		"target": _colored_name(target_id) if not target_id.is_empty() else "",
		"arrow": arrow,
		"quote": _tone(quote, color),
		"action": _tone(action, color),
	}
	var line := template
	for key in fields:
		line = line.replace("{%s}" % key, str(fields[key]))
	if dim or action in _ITEM_EVENTS:
		return "[font_size=12]%s[/font_size]" % line
	return line


func _item_label(item_id: String) -> String:
	if item_id.is_empty():
		return ""
	return str(_ITEM_NAMES.get(item_id, item_id))


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key := event as InputEventKey
		if key.pressed and not key.echo and key.keycode == KEY_N:
			_toggle_notebook()
			get_viewport().set_input_as_handled()


func _toggle_notebook() -> void:
	if _notebook == null:
		return
	_notebook.visible = not _notebook.visible
	if _notebook.visible:
		_log_drawer.visible = false


func _toggle_event_log() -> void:
	_log_drawer.visible = not _log_drawer.visible
	if _log_drawer.visible and _notebook != null:
		_notebook.visible = false


func _toggle_movement() -> void:
	if not _event_log.has_method("set_movement_visible"):
		return
	var show := _move_button.text == "移動"
	_move_button.text = "移動 ▾" if show else "移動"
	_event_log.set_movement_visible(show)


func blocks_pointer(point: Vector2) -> bool:
	var nodes: Array[Control] = [$TopBar, _bottom_bar, _log_button, _log_drawer]
	if _dialogue != null:
		nodes.append(_dialogue)
	if _dialogue_line != null:
		nodes.append(_dialogue_line)
	if _notebook != null:
		nodes.append(_notebook)
	for node in nodes:
		if node != null and node.visible and node.get_global_rect().has_point(point):
			return true
	return false


func note_count() -> int:
	return _note_texts.size()


func dialogue_speaker() -> String:
	return _dialogue_speaker


func set_confront_target(agent_id: String) -> void:
	if _confront_target == agent_id:
		return
	_confront_target = agent_id
	_rebuild_notes()


func set_notes(notes: Variant, ids: Variant = null) -> void:
	_note_texts = PackedStringArray()
	_note_fact_ids = PackedStringArray()
	if typeof(notes) == TYPE_ARRAY:
		for index in notes.size():
			_note_texts.append(str(notes[index]))
			var fact_id := ""
			if typeof(ids) == TYPE_ARRAY and index < ids.size():
				fact_id = str(ids[index])
			_note_fact_ids.append(fact_id)
	_rebuild_notes()


func _rebuild_notes() -> void:
	if _note_box == null:
		return
	for child in _note_box.get_children():
		_note_box.remove_child(child)
		child.free()
	if _note_texts.is_empty():
		var empty := Label.new()
		empty.text = "還沒有筆記。"
		_note_box.add_child(empty)
		return
	for index in _note_texts.size():
		var row := HBoxContainer.new()
		var button := Button.new()
		button.text = "出示"
		var fact_id := str(_note_fact_ids[index])
		button.disabled = _confront_target.is_empty() or fact_id.is_empty()
		button.focus_mode = Control.FOCUS_NONE
		button.custom_minimum_size = Vector2(48, 24)
		button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
		button.pressed.connect(_present_note.bind(fact_id))
		var label := Label.new()
		label.text = str(_note_texts[index])
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(button)
		row.add_child(label)
		_note_box.add_child(row)


func _present_note(fact_id: String) -> void:
	if fact_id.is_empty() or _confront_target.is_empty():
		return
	note_presented.emit(fact_id)


func _build_notebook() -> void:
	_notebook = Panel.new()
	_notebook.name = "Notebook"
	_notebook.visible = false
	_notebook.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_notebook)

	var title := Label.new()
	title.text = "筆記"
	title.theme_type_variation = "Title"
	title.offset_left = 12.0
	title.offset_top = 8.0
	title.offset_right = 120.0
	title.offset_bottom = 32.0
	_notebook.add_child(title)

	var hint := Label.new()
	hint.text = _HINT
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.anchor_right = 1.0
	hint.offset_left = 12.0
	hint.offset_top = 36.0
	hint.offset_right = -12.0
	hint.offset_bottom = 72.0
	_notebook.add_child(hint)

	var scroll := ScrollContainer.new()
	scroll.anchor_right = 1.0
	scroll.anchor_bottom = 1.0
	scroll.offset_left = 12.0
	scroll.offset_top = 76.0
	scroll.offset_right = -12.0
	scroll.offset_bottom = -12.0
	scroll.mouse_filter = Control.MOUSE_FILTER_STOP
	_notebook.add_child(scroll)
	_note_box = VBoxContainer.new()
	_note_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_note_box)
	_rebuild_notes()


func _build_dialogue() -> void:
	var panel := Panel.new()
	panel.name = "Dialogue"
	panel.visible = false
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(panel)
	_dialogue = panel

	var header := HBoxContainer.new()
	header.anchor_right = 1.0
	header.offset_left = 12.0
	header.offset_top = 8.0
	header.offset_right = -12.0
	header.offset_bottom = 36.0
	header.alignment = BoxContainer.ALIGNMENT_CENTER
	panel.add_child(header)

	_dialogue_name = Label.new()
	_dialogue_name.theme_type_variation = "Title"
	_dialogue_name.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	header.add_child(_dialogue_name)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header.add_child(spacer)
	_talk_hunger = _need_label()
	_talk_energy = _need_label()
	_talk_social = _need_label()
	header.add_child(_talk_hunger)
	header.add_child(_talk_energy)
	header.add_child(_talk_social)

	_dialogue_log = RichTextLabel.new()
	_dialogue_log.bbcode_enabled = false
	_dialogue_log.scroll_following = true
	_dialogue_log.anchor_right = 1.0
	_dialogue_log.anchor_bottom = 1.0
	_dialogue_log.offset_left = 12.0
	_dialogue_log.offset_top = 40.0
	_dialogue_log.offset_right = -12.0
	_dialogue_log.offset_bottom = -68.0
	_dialogue_log.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.add_child(_dialogue_log)

	_dialogue_status = Label.new()
	_dialogue_status.anchor_top = 1.0
	_dialogue_status.anchor_right = 1.0
	_dialogue_status.anchor_bottom = 1.0
	_dialogue_status.offset_left = 12.0
	_dialogue_status.offset_top = -64.0
	_dialogue_status.offset_right = -12.0
	_dialogue_status.offset_bottom = -40.0
	panel.add_child(_dialogue_status)

	_dialogue_line = LineEdit.new()
	_dialogue_line.mouse_filter = Control.MOUSE_FILTER_STOP
	_dialogue_line.placeholder_text = _IDLE_PLACEHOLDER
	_dialogue_line.text_submitted.connect(_on_dialogue_submitted)
	add_child(_dialogue_line)


func _need_label() -> Label:
	var label := Label.new()
	label.visible = false
	return label


func _layout_chrome() -> void:
	_place(_dialogue, _DIALOGUE_RECT)
	_place(_notebook, _NOTEBOOK_RECT)
	_place(_log_drawer, _LOG_RECT)
	_place(_log_button, _LOG_BUTTON_RECT)
	_place(_dialogue_line, _INPUT_RECT)
	_fit_bottom_bar()


func _place(node: Control, rect: Rect2) -> void:
	if node == null:
		return
	node.anchor_left = 0.0
	node.anchor_top = 0.0
	node.anchor_right = 0.0
	node.anchor_bottom = 0.0
	node.offset_left = rect.position.x
	node.offset_top = rect.position.y
	node.offset_right = rect.position.x + rect.size.x
	node.offset_bottom = rect.position.y + rect.size.y


func _fit_bottom_bar() -> void:
	var height := _bottom_box.get_combined_minimum_size().y + _bottom_box.offset_top - _bottom_box.offset_bottom
	_bottom_bar.offset_top = _bottom_bar.offset_bottom - height


func _sync_dialogue_chrome() -> void:
	if _dialogue == null:
		return
	_dialogue.visible = not _dialogue_speaker.is_empty()


func _cache_theme_colors() -> void:
	_said_hex = _theme_hex("text")
	_thought_hex = _theme_hex("text_dim")
	_move_hex = _theme_hex("text_dim")
	_name_hex = {
		"mina": _theme_hex("name_mina"),
		"alex": _theme_hex("name_alex"),
		"rin": _theme_hex("name_rin"),
	}


func _theme_hex(item: String) -> String:
	return "#" + ThemeDB.get_project_theme().get_color(item, &"UI").to_html(false)


func _process(delta: float) -> void:
	if not _waiting:
		return
	_dot_accum += delta
	if _dot_accum < 0.4:
		return
	_dot_accum = 0.0
	_dot_phase = (_dot_phase + 1) % 3
	var marks := ["·", "··", "···"]
	_dialogue_status.text = "%s想了想%s" % [_wait_name, marks[_dot_phase]]


func focus_resident(agent_id: String, agent_name: String) -> void:
	_agent_names[agent_id] = agent_name
	_dialogue_speaker = agent_id
	_dialogue_name.text = agent_name
	_dialogue_line.placeholder_text = "跟%s說…" % agent_name
	_sync_dialogue_chrome()
	_apply_talk_needs()
	_dialogue_line.grab_focus()
	dialogue_target_changed.emit()


func note_player_line(text: String) -> void:
	_talk_lines.append("你：%s" % text)
	_refresh_dialogue()


func start_waiting(agent_name: String) -> void:
	_waiting = true
	_wait_name = agent_name
	_dot_phase = 0
	_dot_accum = 0.0
	_dialogue_status.text = "%s想了想·" % agent_name


func stop_waiting() -> void:
	_waiting = false
	_dialogue_status.text = ""


func show_private_reply(speaker_id: String, reply: String) -> void:
	stop_waiting()
	var agent_name := str(_agent_names.get(speaker_id, speaker_id))
	_talk_lines.append("%s對你說：%s" % [agent_name, reply])
	_refresh_dialogue()


func _restore_dialogue(history: Variant) -> void:
	_talk_lines = PackedStringArray()
	var bound := ""
	if typeof(history) == TYPE_ARRAY:
		for turn in history:
			if typeof(turn) != TYPE_DICTIONARY:
				continue
			var reply := str(turn.get("reply", ""))
			if str(turn.get("role", "resident")) == "player":
				_talk_lines.append("你：%s" % reply)
			else:
				var speaker := str(turn.get("speaker_id", ""))
				if not speaker.is_empty():
					bound = speaker
				var agent_name := str(_agent_names.get(speaker, speaker))
				_talk_lines.append("%s對你說：%s" % [agent_name, reply])
	_dialogue_speaker = bound
	if bound.is_empty():
		_dialogue_name.text = ""
		_dialogue_line.placeholder_text = _IDLE_PLACEHOLDER
	else:
		var name := str(_agent_names.get(bound, bound))
		_dialogue_name.text = name
		_dialogue_line.placeholder_text = "跟%s說…" % name
	_sync_dialogue_chrome()
	_apply_talk_needs()
	_refresh_dialogue()
	dialogue_target_changed.emit()


func _refresh_dialogue() -> void:
	if _dialogue_log == null:
		return
	_dialogue_log.text = "\n".join(_talk_lines)


func _on_dialogue_submitted(text: String) -> void:
	var body := text.strip_edges()
	_dialogue_line.text = ""
	if body.is_empty():
		return
	talk_submitted.emit(body)
