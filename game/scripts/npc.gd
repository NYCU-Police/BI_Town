extends Node2D

@export var lerp_speed: float = 8.0

const COLORS := {
	"mina": Color(0.91, 0.45, 0.48),
	"alex": Color(0.35, 0.72, 0.78),
	"rin": Color(0.95, 0.78, 0.35),
}
const SPEECH_HOLD_SECONDS := 6.0
const SPEECH_FADE_SECONDS := 0.4
## Top of the name plate, just above the 16px sprite. The speech tail sits above this.
const LABEL_TOP := -36.0
const SLOT_STEP := 18.0
const BUBBLE_STACK := 78.0
const BUBBLE_MAX_WIDTH := 220.0
const BUBBLE_PAD_X := 10.0
const BUBBLE_PAD_Y := 6.0
const NAME_FONT_SIZE := 11
const TEXT_FONT_SIZE := 14
const TAIL_HALF_WIDTH := 8.0
const TAIL_HEIGHT := 10.0
const NAME_GAP := 2.0
const SPRITE_Y := -8.0
const WALK_FRAME_SECONDS := 0.18
const IDLE_FRAME_SECONDS := 0.7

var server_position: Vector2 = Vector2.ZERO
var visual_offset: Vector2 = Vector2.ZERO
var stand_offset: Vector2 = Vector2.ZERO
var _has_server_position: bool = false
var _speech_hold: float = 0.0
var _speech_fade: float = 0.0
var _agent_id: String = ""
var _visual_id: String = ""
var _slot_index: int = 0
var _anim_time: float = 0.0

@onready var _sprite: Sprite2D = $Sprite
@onready var _label: Label = $Label
@onready var _activity: Label = $Activity
@onready var _speech: Node2D = $Speech
@onready var _bubble: Panel = $Speech/Bubble
@onready var _tail: Polygon2D = $Speech/Tail
@onready var _speaker_label: Label = $Speech/Name
@onready var _speech_label: Label = $Speech/Text


func _ready() -> void:
	_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_sprite.scale = Vector2.ONE
	_sprite.position = Vector2(0, SPRITE_Y)


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
	var tint: Color = COLORS.get(_agent_id, Color(0.93, 0.93, 0.93))
	_label.add_theme_color_override("font_color", tint)
	if _agent_id != _visual_id:
		_visual_id = _agent_id
		VisualBinder.apply(_sprite, self, _agent_id)
	var task := str(data.get("activity", "")).strip_edges()
	if task.is_empty():
		_activity.visible = false
		_activity.text = ""
	else:
		_activity.text = "%s中" % task
		_activity.visible = true

	_place(snap)


func set_stand_offset(offset: Vector2, snap: bool) -> void:
	stand_offset = offset
	_place(snap)


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
	var speaker_color: Color = COLORS.get(_agent_id, Color(0.2, 0.2, 0.22))
	_speaker_label.add_theme_color_override("font_color", speaker_color)
	_speech_label.text = utterance
	_layout_bubble()
	_speech.modulate.a = 1.0
	_speech.visible = true
	_speech_hold = SPEECH_HOLD_SECONDS
	_speech_fade = 0.0


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
	if absf(moved.x) > 0.15:
		_sprite.flip_h = moved.x < 0.0
	var traveling := moved.length() > 0.25 or position.distance_to(goal) > 0.8
	_anim_time += delta
	var lift := 0.0
	if traveling:
		var frame := int(_anim_time / WALK_FRAME_SECONDS) % 2
		lift = 1.0 if frame == 1 else 0.0
	else:
		var frame := int(_anim_time / IDLE_FRAME_SECONDS) % 2
		lift = 1.0 if frame == 1 else 0.0
	_sprite.position = Vector2(0, SPRITE_Y - lift)
