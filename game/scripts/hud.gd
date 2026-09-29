extends CanvasLayer

signal talk_submitted(text: String)
signal note_presented(fact_id: String)
signal dialogue_target_changed
signal accuse_submitted(culprit_id: String, motive_id: String)
signal next_round_submitted

const _Places := preload("res://scripts/place_names.gd")
## Same line as the server's hungry / exhausted / lonely marks.
const _LOW_NEED := 30
const _MOTION_SEC := 0.15
const _NOTE_FLASH_SEC := 0.4
const _DOT_SEC := 0.4
const _NEED_PULSE_SEC := 1.0
const _NEED_PULSE_MIN := 0.6
const _ACTION_HINT_SEC := 1.0
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
var _assembly: Panel
var _person_pick: OptionButton
var _motive_pick: OptionButton
var _assembly_body: RichTextLabel
var _assembly_status: Label
var _assembly_count: Label
var _assembly_confirm: Button
var _assembly_next: Button
var _assembly_left := 0.0
var _assembly_timing := false
var _waiting := false
var _wait_name := ""
var _dot_phase := 0
var _dot_accum := 0.0
var _seen_name := ""
var _seen_hunger := 0
var _seen_energy := 0
var _seen_social := 0
var _seen_ready := false
var _you := ""
var _notes_ready := false
var _need_levels: Array[int] = [100, 100, 100]
var _pulse_clock := 0.0
var _dialogue_shown := false
var _notebook_open := false
var _log_open := false
var _hint_token := 0
var _fades: Dictionary = {}
var _present_caption: Label


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
	_build_assembly()
	_log_drawer.modulate.a = 0.0
	_layout_chrome()


func apply_snapshot(data: Dictionary) -> void:
	_you = str(data.get("you", ""))
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
	_restore_round(data)
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
	_flash_player_action(data)


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
	_need_levels = [hunger, energy, social]
	_paint_need(_hunger_label, "飢餓", hunger)
	_paint_need(_energy_label, "體力", energy)
	_paint_need(_social_label, "社交", social)
	_pulse_needs(0.0)


func show_intent_reason(reason: String) -> void:
	_hint_token += 1
	_intent_label.theme_type_variation = "Warn"
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
	"said": "{time} {name}{public}{arrow}\n{quote}",
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
	var dim := action == "thought" or action == "said" or action in _MOVE_EVENTS
	var color := _thought_hex if action == "thought" or action == "said" else (
		_move_hex if action in _MOVE_EVENTS else _said_hex
	)
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
		"public": _tone("（公開）", color) if action == "said" else "",
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
	_notebook_open = not _notebook_open
	_fade(_notebook, _notebook_open)
	if _notebook_open and _log_open:
		_log_open = false
		_fade(_log_drawer, false)


func _toggle_event_log() -> void:
	_log_open = not _log_open
	_fade(_log_drawer, _log_open)
	if _log_open and _notebook_open:
		_notebook_open = false
		_fade(_notebook, false)


func _toggle_movement() -> void:
	if not _event_log.has_method("set_movement_visible"):
		return
	var show := _move_button.text == "移動"
	_move_button.text = "移動 ▾" if show else "移動"
	_event_log.set_movement_visible(show)


func blocks_pointer(point: Vector2) -> bool:
	var nodes: Array[Control] = [$TopBar, _bottom_bar, _log_button, _log_drawer]
	if _assembly != null:
		nodes.append(_assembly)
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
	var changed := _confront_target != agent_id
	_confront_target = agent_id
	_refresh_present_caption()
	if changed:
		_rebuild_notes()


func set_notes(notes: Variant, ids: Variant = null) -> void:
	var previous := _note_texts.size()
	var first_load := not _notes_ready
	_notes_ready = true
	_note_texts = PackedStringArray()
	_note_fact_ids = PackedStringArray()
	if typeof(notes) == TYPE_ARRAY:
		for index in notes.size():
			_note_texts.append(str(notes[index]))
			var fact_id := ""
			if typeof(ids) == TYPE_ARRAY and index < ids.size():
				fact_id = str(ids[index])
			_note_fact_ids.append(fact_id)
	_rebuild_notes(_note_texts.size() if first_load else previous)


func _rebuild_notes(flash_from: int = -1) -> void:
	if _note_box == null:
		return
	if flash_from < 0:
		flash_from = _note_texts.size()
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
		var fact_id := str(_note_fact_ids[index])
		if not fact_id.is_empty():
			var button := Button.new()
			button.text = "出示"
			button.disabled = _confront_target.is_empty()
			button.focus_mode = Control.FOCUS_NONE
			button.custom_minimum_size = Vector2(48, 24)
			button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
			button.pressed.connect(_present_note.bind(fact_id))
			row.add_child(button)
		var label := Label.new()
		label.text = str(_note_texts[index])
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(label)
		if index >= flash_from:
			var flash := PanelContainer.new()
			flash.theme_type_variation = "Flash"
			flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
			flash.add_child(row)
			_note_box.add_child(flash)
			var tween := create_tween()
			tween.tween_property(flash, "self_modulate:a", 0.0, _NOTE_FLASH_SEC)
		else:
			_note_box.add_child(row)


func _present_note(fact_id: String) -> void:
	if fact_id.is_empty() or _confront_target.is_empty():
		return
	note_presented.emit(fact_id)


func _build_notebook() -> void:
	_notebook = Panel.new()
	_notebook.name = "Notebook"
	_notebook.visible = false
	_notebook.modulate.a = 0.0
	_notebook.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_notebook)

	var title := Label.new()
	title.text = "筆記"
	title.theme_type_variation = "Title"
	title.offset_left = 12.0
	title.offset_top = 8.0
	title.offset_right = 72.0
	title.offset_bottom = 32.0
	_notebook.add_child(title)

	_present_caption = Label.new()
	_present_caption.text = "走到對方面前才能出示"
	_present_caption.anchor_right = 1.0
	_present_caption.offset_left = 76.0
	_present_caption.offset_top = 14.0
	_present_caption.offset_right = -12.0
	_present_caption.offset_bottom = 32.0
	_notebook.add_child(_present_caption)

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
	panel.modulate.a = 0.0
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
	var open := not _dialogue_speaker.is_empty()
	if open == _dialogue_shown:
		return
	_dialogue_shown = open
	_fade(_dialogue, open)


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
	_pulse_needs(delta)
	if _assembly_timing:
		_assembly_left = max(0.0, _assembly_left - delta)
		if _assembly_count != null:
			_assembly_count.text = "剩下 %d 秒" % int(ceil(_assembly_left))
	if not _waiting:
		return
	_dot_accum += delta
	if _dot_accum < _DOT_SEC:
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
	if _dialogue_line != null:
		_dialogue_line.editable = false
		_dialogue_line.release_focus()


func stop_waiting() -> void:
	_waiting = false
	_dialogue_status.text = ""
	if _dialogue_line == null:
		return
	_dialogue_line.editable = true
	_dialogue_line.grab_focus()


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
	if body.is_empty() or not _dialogue_line.editable:
		return
	talk_submitted.emit(body)


func _refresh_present_caption() -> void:
	if _present_caption == null:
		return
	if _confront_target.is_empty():
		_present_caption.text = "走到對方面前才能出示"
		return
	var name := str(_agent_names.get(_confront_target, ""))
	if name.is_empty() and _dialogue_name != null:
		name = _dialogue_name.text
	_present_caption.text = "可向 %s 出示" % name


func _flash_player_action(data: Dictionary) -> void:
	if _you.is_empty() or str(data.get("agent_id", "")) != _you:
		return
	var action := str(data.get("event", ""))
	if action == "picked_up":
		_flash_hint("撿到了")
	elif action == "gave" and str(data.get("item", "")) == "bread":
		_flash_hint("麵包送出了")
	elif action == "gave":
		_flash_hint("送出了")


func _flash_hint(text: String) -> void:
	_hint_token += 1
	var token := _hint_token
	_intent_label.theme_type_variation = "Accent"
	_intent_label.text = text
	_intent_label.visible = true
	var tween := create_tween()
	tween.tween_interval(_ACTION_HINT_SEC)
	tween.tween_callback(func() -> void:
		if token != _hint_token:
			return
		_intent_label.text = ""
		_intent_label.visible = false
		_intent_label.theme_type_variation = "Warn"
	)


func _fade(node: CanvasItem, show: bool) -> void:
	if node == null:
		return
	var key := node.get_instance_id()
	if _fades.has(key):
		var previous: Tween = _fades[key]
		if previous != null and previous.is_valid():
			previous.kill()
	var tween := create_tween()
	_fades[key] = tween
	tween.set_trans(Tween.TRANS_LINEAR)
	if show:
		node.visible = true
		node.modulate.a = 0.0
		tween.tween_property(node, "modulate:a", 1.0, _MOTION_SEC)
		return
	if not node.visible:
		return
	tween.tween_property(node, "modulate:a", 0.0, _MOTION_SEC)
	tween.tween_callback(func() -> void:
		node.visible = false
	)


func _pulse_needs(delta: float) -> void:
	_pulse_clock += delta
	var phase := fmod(_pulse_clock, _NEED_PULSE_SEC) / _NEED_PULSE_SEC
	var dip := 0.5 - 0.5 * cos(phase * TAU)
	var alpha := lerpf(1.0, _NEED_PULSE_MIN, dip)
	var labels: Array[Label] = [_hunger_label, _energy_label, _social_label]
	for index in labels.size():
		var label := labels[index]
		if label == null:
			continue
		var low := index < _need_levels.size() and _need_levels[index] < _LOW_NEED
		label.modulate.a = alpha if low else 1.0


func show_assembly(message: Dictionary) -> void:
	if _assembly == null:
		return
	_fill_options(_person_pick, message.get("residents", []), "name", "id")
	_fill_options(_motive_pick, message.get("motives", []), "label", "id")
	_assembly_body.text = "鎮民大會。選出犯人與動機。"
	_assembly_status.text = ""
	_assembly_confirm.visible = true
	_assembly_confirm.disabled = false
	_person_pick.disabled = false
	_motive_pick.disabled = false
	_assembly_next.visible = false
	_assembly.visible = true
	_start_countdown(int(message.get("remaining_seconds", 90)))


func mark_accused() -> void:
	if _assembly == null:
		return
	_assembly_confirm.disabled = true
	_person_pick.disabled = true
	_motive_pick.disabled = true
	_assembly_status.text = "等其他人"


func show_reveal(message: Dictionary) -> void:
	if _assembly == null:
		return
	var score := int(message.get("score", 0))
	_assembly_body.text = "%s\n\n你的分數：%d" % [str(message.get("text", "")), score]
	_assembly_status.text = ""
	_assembly_confirm.visible = false
	_assembly_next.visible = true
	_assembly_next.disabled = false
	_person_pick.visible = false
	_motive_pick.visible = false
	_assembly.visible = true
	_start_countdown(int(message.get("remaining_seconds", 45)))


func hide_assembly() -> void:
	_assembly_timing = false
	if _assembly != null:
		_assembly.visible = false
	if _person_pick != null:
		_person_pick.visible = true
	if _motive_pick != null:
		_motive_pick.visible = true


func _restore_round(data: Dictionary) -> void:
	var phase := str(data.get("phase", "play"))
	if phase == "assembly":
		show_assembly(data)
		if bool(data.get("accused", false)):
			mark_accused()
	elif phase == "reveal":
		show_reveal(data)
	else:
		hide_assembly()


func _start_countdown(seconds: int) -> void:
	_assembly_left = float(seconds)
	_assembly_timing = true
	if _assembly_count != null:
		_assembly_count.text = "剩下 %d 秒" % seconds


func _fill_options(picker: OptionButton, rows: Variant, label_key: String, id_key: String) -> void:
	picker.clear()
	picker.visible = true
	if typeof(rows) != TYPE_ARRAY:
		return
	for row in rows:
		if typeof(row) != TYPE_DICTIONARY:
			continue
		picker.add_item(str(row.get(label_key, "")))
		picker.set_item_metadata(picker.item_count - 1, str(row.get(id_key, "")))


func _build_assembly() -> void:
	_assembly = Panel.new()
	_assembly.name = "Assembly"
	_assembly.visible = false
	_assembly.anchor_left = 0.5
	_assembly.anchor_top = 0.5
	_assembly.anchor_right = 0.5
	_assembly.anchor_bottom = 0.5
	_assembly.offset_left = -220.0
	_assembly.offset_top = -180.0
	_assembly.offset_right = 220.0
	_assembly.offset_bottom = 180.0
	_assembly.mouse_filter = Control.MOUSE_FILTER_STOP
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#1c1916")
	style.set_corner_radius_all(6)
	_assembly.add_theme_stylebox_override("panel", style)
	add_child(_assembly)

	_assembly_body = RichTextLabel.new()
	_assembly_body.offset_left = 16.0
	_assembly_body.offset_top = 12.0
	_assembly_body.offset_right = 424.0
	_assembly_body.offset_bottom = 150.0
	_assembly_body.scroll_active = true
	_assembly_body.add_theme_color_override("default_color", Color("#f4f0e6"))
	_assembly.add_child(_assembly_body)

	_person_pick = _dark_option()
	_person_pick.offset_top = 160.0
	_person_pick.offset_bottom = 192.0
	_assembly.add_child(_person_pick)
	_motive_pick = _dark_option()
	_motive_pick.offset_top = 200.0
	_motive_pick.offset_bottom = 232.0
	_assembly.add_child(_motive_pick)

	_assembly_status = Label.new()
	_assembly_status.offset_left = 16.0
	_assembly_status.offset_top = 240.0
	_assembly_status.offset_right = 220.0
	_assembly_status.offset_bottom = 268.0
	_assembly_status.add_theme_color_override("font_color", Color("#f4f0e6"))
	_assembly.add_child(_assembly_status)

	_assembly_count = Label.new()
	_assembly_count.offset_left = 230.0
	_assembly_count.offset_top = 240.0
	_assembly_count.offset_right = 424.0
	_assembly_count.offset_bottom = 268.0
	_assembly_count.add_theme_color_override("font_color", Color("#f4f0e6"))
	_assembly.add_child(_assembly_count)

	_assembly_confirm = Button.new()
	_assembly_confirm.text = "確認"
	_assembly_confirm.offset_left = 16.0
	_assembly_confirm.offset_top = 276.0
	_assembly_confirm.offset_right = 140.0
	_assembly_confirm.offset_bottom = 312.0
	_assembly_confirm.pressed.connect(_submit_accusation)
	_assembly.add_child(_assembly_confirm)

	_assembly_next = Button.new()
	_assembly_next.text = "下一局"
	_assembly_next.visible = false
	_assembly_next.offset_left = 16.0
	_assembly_next.offset_top = 276.0
	_assembly_next.offset_right = 140.0
	_assembly_next.offset_bottom = 312.0
	_assembly_next.pressed.connect(_submit_next_round)
	_assembly.add_child(_assembly_next)


func _dark_option() -> OptionButton:
	var picker := OptionButton.new()
	picker.offset_left = 16.0
	picker.offset_right = 424.0
	picker.add_theme_color_override("font_color", Color("#f4f0e6"))
	picker.add_theme_color_override("font_hover_color", Color("#f4f0e6"))
	return picker


func _submit_accusation() -> void:
	if _person_pick.item_count == 0 or _motive_pick.item_count == 0:
		return
	var culprit := str(_person_pick.get_item_metadata(_person_pick.selected))
	var motive := str(_motive_pick.get_item_metadata(_motive_pick.selected))
	accuse_submitted.emit(culprit, motive)


func _submit_next_round() -> void:
	_assembly_next.disabled = true
	_assembly_status.text = "等這一局結束"
	next_round_submitted.emit()
