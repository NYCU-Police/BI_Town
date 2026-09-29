extends Node2D

@export var lerp_speed: float = 8.0

const SPEECH_HOLD_SECONDS := 6.0
const SPEECH_FADE_SECONDS := 0.4
## Top of the name plate, just above the 16px sprite. The speech tail sits above this.
const LABEL_TOP := -40.0
## Same band as map decorations so Y-sort can hide a character behind a tree.
const CHARACTER_Z := 1
const LOCAL_PLAYER_Z := 1
const SLOT_STEP := 18.0
const BUBBLE_STACK := 78.0
const BUBBLE_MAX_WIDTH := 220.0
const BUBBLE_PAD_X := 10.0
const BUBBLE_PAD_Y := 6.0
const NAME_FONT_SIZE := 12
const TEXT_FONT_SIZE := 12
const TAIL_HALF_WIDTH := 8.0
const TAIL_HEIGHT := 10.0
const NAME_GAP := 2.0
const SHEET_FPS := 8.0
## Same cutoff as HUD and backend NEED_HUNGRY. Presentation only.
const _HUNGRY_BELOW := 30
## Matches backend EAT_FULLNESS_RESTORE.
const _EAT_HUNGER := 35
const _CHAT_SECONDS := 3.0

var server_position: Vector2 = Vector2.ZERO
var visual_offset: Vector2 = Vector2.ZERO
var stand_offset: Vector2 = Vector2.ZERO
var _has_server_position: bool = false
var _speech_hold: float = 0.0
var _speech_fade: float = 0.0
var _agent_id: String = ""
var _visual_id: String = ""
var _slot_index: int = 0
var _facing := "down"
var _frame_index := 0
var _frame_clock := 0.0
var _local_player: bool = false
var _name_drop := 0.0
var _hop := 0.0
var _chat_left := 0.0
var _conversing := false
var _status_fx := ""
var _hungry := false
var _collapsed := false

var _emote: Sprite2D
var _held: Sprite2D
var _dust: GPUParticles2D
var _float_label: Label

var _you_ring: Line2D
var _you_arrow: Polygon2D

@onready var _sprite: Sprite2D = $Sprite
@onready var _name_plate: Panel = $NamePlate
@onready var _label: Label = $Label
@onready var _activity: Label = $Activity
@onready var _speech: Node2D = $Speech
@onready var _bubble: Panel = $Speech/Bubble
@onready var _tail: Polygon2D = $Speech/Tail
@onready var _speaker_label: Label = $Speech/Name
@onready var _speech_label: Label = $Speech/Text


func _ready() -> void:
	z_index = CHARACTER_Z
	y_sort_enabled = true
	_name_plate.z_index = 20
	_label.z_index = 20
	_activity.z_index = 20
	_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_sprite.scale = Vector2.ONE
	_sprite.position = Vector2.ZERO
	_you_ring = Line2D.new()
	_you_ring.name = "YouRing"
	_you_ring.width = 2.0
	_you_ring.closed = true
	_you_ring.visible = false
	_you_ring.z_index = 0
	_you_ring.points = _circle_points(11.0, 16)
	add_child(_you_ring)
	move_child(_you_ring, 0)
	_you_arrow = Polygon2D.new()
	_you_arrow.name = "YouArrow"
	_you_arrow.polygon = PackedVector2Array([
		Vector2(-5, -34),
		Vector2(5, -34),
		Vector2(0, -22),
	])
	_you_arrow.visible = false
	add_child(_you_arrow)
	_emote = Sprite2D.new()
	_emote.name = "Emote"
	_emote.position = Vector2(0, -28)
	_emote.z_index = 20
	_emote.visible = false
	add_child(_emote)
	_held = Sprite2D.new()
	_held.name = "HeldItem"
	_held.position = Vector2(12, -2)
	_held.z_index = 2
	_held.visible = false
	add_child(_held)
	_dust = GPUParticles2D.new()
	_dust.name = "Dust"
	_dust.z_index = 0
	_dust.amount = 4
	_dust.lifetime = 0.35
	_dust.explosiveness = 0.0
	_dust.local_coords = true
	_dust.emitting = false
	_dust.visibility_rect = Rect2(-12, -8, 24, 16)
	_dust.texture = _dust_texture()
	_dust.process_material = _dust_material()
	add_child(_dust)
	_float_label = Label.new()
	_float_label.name = "FloatText"
	_float_label.visible = false
	_float_label.z_index = 30
	_float_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_float_label.add_theme_font_size_override("font_size", 12)
	_float_label.add_theme_color_override("font_color", Color(1, 0.95, 0.8))
	_float_label.add_theme_color_override("font_outline_color", Color(0.08, 0.06, 0.04))
	_float_label.add_theme_constant_override("outline_size", 2)
	add_child(_float_label)


func server_anchor() -> Vector2:
	return server_position


func update_from_server(data: Dictionary, snap: bool = false) -> void:
	var pos: Variant = data.get("position", {})
	if typeof(pos) != TYPE_DICTIONARY:
		push_error("NPC update missing position: %s" % str(data))
		return

	var coords: Dictionary = pos
	server_position = Vector2(float(coords.get("x", 0.0)), float(coords.get("y", 0.0)))
	_agent_id = str(data.get("id", ""))
	_label.text = str(data.get("name", _agent_id if not _agent_id.is_empty() else "NPC"))
	var tint := VisualBinder.name_color("agent." + _agent_id)
	_label.add_theme_color_override("font_color", tint)
	if _agent_id != _visual_id:
		_visual_id = _agent_id
		VisualBinder.apply(_sprite, self, "agent." + _agent_id)
	var task := str(data.get("activity", "")).strip_edges()
	if task.is_empty():
		_activity.visible = false
		_activity.text = ""
	else:
		_activity.text = "%s中" % task
		_activity.visible = true

	_place(snap)
	_show_held(data)
	_read_needs(data)
	_refresh_status_emote()
	if _local_player:
		_show_you()


func set_local_player(enabled: bool) -> void:
	_local_player = enabled
	if enabled:
		_show_you()
		return
	z_index = CHARACTER_Z
	if _you_ring != null:
		_you_ring.visible = false
	if _you_arrow != null:
		_you_arrow.visible = false
	_apply_name_plate()


func _show_you() -> void:
	_label.text = "你"
	var tint := VisualBinder.name_color("agent.player")
	_label.add_theme_color_override("font_color", tint)
	_apply_name_plate()
	_you_arrow.color = tint
	_you_arrow.visible = true
	_you_ring.default_color = Color(tint.r, tint.g, tint.b, 0.95)
	_you_ring.visible = true
	z_index = LOCAL_PLAYER_Z
	var fallback := get_node_or_null("Fallback")
	if fallback != null:
		for child in fallback.get_children():
			if child is Label:
				(child as CanvasItem).visible = false


func _circle_points(radius: float, count: int) -> PackedVector2Array:
	var points := PackedVector2Array()
	for index in count:
		var angle := TAU * float(index) / float(count)
		points.append(Vector2(cos(angle), sin(angle)) * radius)
	return points


func set_stand_offset(offset: Vector2, snap: bool) -> void:
	stand_offset = offset
	_place(snap)


func set_name_drop(drop: float) -> void:
	if is_equal_approx(_name_drop, drop):
		return
	_name_drop = drop
	_apply_name_plate()


func _apply_name_plate() -> void:
	if _name_plate == null or _label == null:
		return
	var top := (-52.0 if _local_player else -40.0) + _name_drop
	var bottom := top + 16.0
	_name_plate.offset_top = top
	_name_plate.offset_bottom = bottom
	_label.offset_top = top
	_label.offset_bottom = bottom


func set_cluster_slot(index: int, count: int, snap: bool) -> void:
	_slot_index = index
	var body := Vector2.ZERO
	if count > 1:
		var origin := -SLOT_STEP * float(count - 1) / 2.0
		body = Vector2(origin + SLOT_STEP * float(index), 0.0)
	visual_offset = body
	_place_speech()
	_place(snap)


func show_speech(content: String) -> void:
	var utterance := content.strip_edges()
	if utterance.is_empty():
		return
	_speaker_label.text = _label.text
	_speech_label.text = utterance
	_layout_bubble()
	_speech.modulate.a = 1.0
	_speech.visible = true
	_speech_hold = SPEECH_HOLD_SECONDS
	_speech_fade = 0.0
	show_chat_emote()


func _place_speech() -> void:
	# Tail tip is just above the name plate. Extra people stack upward.
	_speech.position = Vector2(0, LABEL_TOP - 2.0 - BUBBLE_STACK * float(_slot_index))


func _layout_bubble() -> void:
	var font := _speech_label.get_theme_font("font")
	var inner := BUBBLE_MAX_WIDTH - BUBBLE_PAD_X * 2.0
	var breaks := TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND | TextServer.BREAK_ADAPTIVE
	var name_size := font.get_string_size(
		_speaker_label.text,
		HORIZONTAL_ALIGNMENT_CENTER,
		-1,
		NAME_FONT_SIZE,
	)
	var text_size := font.get_multiline_string_size(
		_speech_label.text,
		HORIZONTAL_ALIGNMENT_CENTER,
		inner,
		TEXT_FONT_SIZE,
		-1,
		breaks,
	)
	var content_w := maxf(name_size.x, minf(text_size.x, inner))
	var box_w := clampf(content_w + BUBBLE_PAD_X * 2.0, 48.0, BUBBLE_MAX_WIDTH)
	var box_h := BUBBLE_PAD_Y + name_size.y + NAME_GAP + text_size.y + BUBBLE_PAD_Y
	var box_bottom := -TAIL_HEIGHT
	var box_top := box_bottom - box_h
	var box_left := -box_w / 2.0
	_bubble.offset_left = box_left
	_bubble.offset_top = box_top
	_bubble.offset_right = box_left + box_w
	_bubble.offset_bottom = box_bottom
	var text_left := box_left + BUBBLE_PAD_X
	var text_right := box_left + box_w - BUBBLE_PAD_X
	var name_top := box_top + BUBBLE_PAD_Y
	_speaker_label.offset_left = text_left
	_speaker_label.offset_top = name_top
	_speaker_label.offset_right = text_right
	_speaker_label.offset_bottom = name_top + name_size.y
	var body_top := name_top + name_size.y + NAME_GAP
	_speech_label.offset_left = text_left
	_speech_label.offset_top = body_top
	_speech_label.offset_right = text_right
	_speech_label.offset_bottom = body_top + text_size.y
	_tail.polygon = PackedVector2Array([
		Vector2(-TAIL_HALF_WIDTH, box_bottom + 1.0),
		Vector2(TAIL_HALF_WIDTH, box_bottom + 1.0),
		Vector2(0.0, 0.0),
	])


func _goal() -> Vector2:
	return server_position + stand_offset + visual_offset


func _place(snap: bool) -> void:
	if snap or not _has_server_position:
		position = _goal()
		_has_server_position = true


func _process(delta: float) -> void:
	if _chat_left > 0.0:
		_chat_left -= delta
		if _chat_left <= 0.0:
			_refresh_status_emote()
	if _speech.visible:
		if _speech_hold > 0.0:
			_speech_hold -= delta
			if _speech_hold <= 0.0:
				_speech_fade = SPEECH_FADE_SECONDS
		elif _speech_fade > 0.0:
			_speech_fade -= delta
			_speech.modulate.a = clampf(_speech_fade / SPEECH_FADE_SECONDS, 0.0, 1.0)
			if _speech_fade <= 0.0:
				_speech.visible = false
				_speech_label.text = ""
				_speaker_label.text = ""
				_speech.modulate.a = 1.0
	if not _has_server_position:
		return
	var goal := _goal()
	var before := position
	position = position.lerp(goal, clampf(lerp_speed * delta, 0.0, 1.0))
	_apply_motion(delta, position - before, goal)


func _apply_motion(delta: float, moved: Vector2, goal: Vector2) -> void:
	_sprite.flip_h = false
	var traveling := moved.length() > 0.25 or position.distance_to(goal) > 0.8
	_sprite.position = Vector2(0, -_hop)
	if _dust != null:
		_dust.emitting = traveling
	if not _sprite.has_meta("sheet_anims"):
		return
	var anims: Dictionary = _sprite.get_meta("sheet_anims")
	var next_facing := _facing
	if absf(moved.x) > absf(moved.y) and absf(moved.x) > 0.15:
		next_facing = "left" if moved.x < 0.0 else "right"
	elif absf(moved.y) > 0.15:
		next_facing = "down" if moved.y > 0.0 else "up"
	if next_facing != _facing:
		_facing = next_facing
		_frame_index = 0
		_frame_clock = 0.0
	var frames: Array = anims.get(("walk_" if traveling else "idle_") + _facing, [])
	if frames.is_empty():
		return
	if traveling:
		_frame_clock += delta
		if _frame_clock >= 1.0 / SHEET_FPS:
			_frame_clock = 0.0
			_frame_index = (_frame_index + 1) % frames.size()
	else:
		_frame_index = 0
		_frame_clock = 0.0
	var cell: Variant = frames[_frame_index % frames.size()]
	var frame: Vector2 = _sprite.get_meta("sheet_frame")
	var column := 0
	var row := 0
	if typeof(cell) == TYPE_ARRAY and cell.size() >= 2:
		column = int(cell[0])
		row = int(cell[1])
	_sprite.region_enabled = true
	_sprite.region_rect = Rect2(float(column) * frame.x, float(row) * frame.y, frame.x, frame.y)


func react(action: String, item_id: String) -> void:
	match action:
		"ate":
			_hop_up()
			_float("+%d 飽食" % _EAT_HUNGER)
		"picked_up":
			_hop_up()
			_float("+%s" % _item_name(item_id))
		"gave":
			_hop_up()
			_float("送出 %s" % _item_name(item_id))


func show_chat_emote() -> void:
	_chat_left = _CHAT_SECONDS
	_show_fx("fx.chat")


func set_conversing(active: bool) -> void:
	_conversing = active
	if active:
		_show_fx("fx.chat")
		return
	_chat_left = 0.0
	_refresh_status_emote()


func _read_needs(data: Dictionary) -> void:
	_collapsed = bool(data.get("collapsed", false))
	_hungry = false
	var needs: Variant = data.get("needs", {})
	if typeof(needs) == TYPE_DICTIONARY:
		_hungry = int(needs.get("hunger", 100)) < _HUNGRY_BELOW


func _refresh_status_emote() -> void:
	if _conversing:
		_show_fx("fx.chat")
		return
	if _chat_left > 0.0:
		return
	if _collapsed:
		_show_fx("fx.collapsed")
	elif _hungry:
		_show_fx("fx.hungry")
	else:
		_clear_fx()


func _show_fx(content_id: String) -> void:
	if _emote == null:
		return
	if _status_fx == content_id and _emote.visible:
		return
	_status_fx = content_id
	VisualBinder.apply(_emote, self, content_id)
	_emote.visible = _emote.texture != null


func _clear_fx() -> void:
	_status_fx = ""
	if _emote == null:
		return
	_emote.visible = false


func _show_held(data: Dictionary) -> void:
	if _held == null:
		return
	var item_id := ""
	var stacks: Variant = data.get("items", [])
	if typeof(stacks) == TYPE_ARRAY and not stacks.is_empty():
		var stack: Variant = stacks[0]
		if typeof(stack) == TYPE_DICTIONARY:
			item_id = str(stack.get("id", ""))
	if item_id.is_empty():
		_held.visible = false
		return
	VisualBinder.apply(_held, self, "item.%s" % item_id)
	_held.visible = true


func _hop_up() -> void:
	var tween := create_tween()
	tween.tween_method(_set_hop, 0.0, 4.0, 0.08)
	tween.tween_method(_set_hop, 4.0, 0.0, 0.12)


func _set_hop(value: float) -> void:
	_hop = value


func _float(text: String) -> void:
	if _float_label == null or text.is_empty():
		return
	_float_label.text = text
	_float_label.position = Vector2(-36, -46)
	_float_label.size = Vector2(72, 16)
	_float_label.modulate.a = 1.0
	_float_label.visible = true
	var tween := create_tween()
	tween.set_parallel(true)
	tween.tween_property(_float_label, "position", Vector2(-36, -68), 0.7)
	tween.tween_property(_float_label, "modulate:a", 0.0, 0.7)
	tween.chain().tween_callback(_float_label.hide)


func _item_name(item_id: String) -> String:
	match item_id:
		"bread":
			return "麵包"
		"wood":
			return "木材"
		"watering_can":
			return "澆水壺"
		_:
			return item_id


func _dust_texture() -> Texture2D:
	var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.78, 0.72, 0.58, 0.85))
	return ImageTexture.create_from_image(image)


func _dust_material() -> ParticleProcessMaterial:
	var material := ParticleProcessMaterial.new()
	material.particle_flag_disable_z = true
	material.direction = Vector3(0, -1, 0)
	material.spread = 35.0
	material.initial_velocity_min = 3.0
	material.initial_velocity_max = 8.0
	material.gravity = Vector3(0, 18, 0)
	material.scale_min = 1.0
	material.scale_max = 1.0
	return material
