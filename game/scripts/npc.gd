extends Node2D

@export var lerp_speed: float = 8.0

const COLORS := {
	"mina": Color(0.91, 0.45, 0.48),
	"alex": Color(0.35, 0.72, 0.78),
	"rin": Color(0.95, 0.78, 0.35),
}
const SPEECH_HOLD_SECONDS := 6.0
const SPEECH_FADE_SECONDS := 0.4
const LABEL_TOP := -32.0
const LABEL_BOTTOM := -12.0
const STACK_LIFT := 22.0
const BUBBLE_STACK := 64.0
const BODY_STEP := 26.0
const BUBBLE_MAX_WIDTH := 220.0
const BUBBLE_PAD_X := 10.0
const BUBBLE_PAD_Y := 8.0
const TAIL_HALF_WIDTH := 8.0
const TAIL_HEIGHT := 10.0

var server_position: Vector2 = Vector2.ZERO
var visual_offset: Vector2 = Vector2.ZERO
var _has_server_position: bool = false
var _speech_hold: float = 0.0
var _speech_fade: float = 0.0

@onready var _body: ColorRect = $Body
@onready var _label: Label = $Label
@onready var _speech: Node2D = $Speech
@onready var _bubble: Panel = $Speech/Bubble
@onready var _tail: Polygon2D = $Speech/Tail
@onready var _speech_label: Label = $Speech/Text


func server_anchor() -> Vector2:
	return server_position


func update_from_server(data: Dictionary, snap: bool = false) -> void:
	var pos: Variant = data.get("position", {})
	if typeof(pos) != TYPE_DICTIONARY:
		push_error("NPC update missing position: %s" % str(data))
		return

	var coords: Dictionary = pos
	server_position = Vector2(float(coords.get("x", 0.0)), float(coords.get("y", 0.0)))
	_label.text = str(data.get("name", data.get("id", "NPC")))

	var agent_id := str(data.get("id", ""))
	if COLORS.has(agent_id):
		_body.color = COLORS[agent_id]

	_place(snap)


func set_cluster_slot(index: int, count: int, snap: bool) -> void:
	var body := Vector2.ZERO
	if count > 1:
		var origin := -BODY_STEP * float(count - 1) / 2.0
		body = Vector2(origin + BODY_STEP * float(index), 0.0)
	visual_offset = body
	var lift := STACK_LIFT * float(index)
	_label.offset_top = LABEL_TOP - lift
	_label.offset_bottom = LABEL_BOTTOM - lift
	_speech.position = Vector2(0, LABEL_TOP - 10.0 - BUBBLE_STACK * float(index))
	_place(snap)


func show_speech(content: String) -> void:
	var utterance := content.strip_edges()
	if utterance.is_empty():
		return
	_speech_label.text = utterance
	_layout_bubble()
	_speech.modulate.a = 1.0
	_speech.visible = true
	_speech_hold = SPEECH_HOLD_SECONDS
	_speech_fade = 0.0


func _layout_bubble() -> void:
	var font := _speech_label.get_theme_font("font")
	var font_size := _speech_label.get_theme_font_size("font_size")
	var inner := BUBBLE_MAX_WIDTH - BUBBLE_PAD_X * 2.0
	# WORD_SMART, so Chinese wraps on character boundaries instead of overflowing.
	var breaks := TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND | TextServer.BREAK_ADAPTIVE
	var measured := font.get_multiline_string_size(
		_speech_label.text,
		HORIZONTAL_ALIGNMENT_CENTER,
		inner,
		font_size,
		-1,
		breaks,
	)
	var box_w := clampf(measured.x + BUBBLE_PAD_X * 2.0, 36.0, BUBBLE_MAX_WIDTH)
	var box_h := measured.y + BUBBLE_PAD_Y * 2.0
	var box_bottom := -TAIL_HEIGHT
	var box_top := box_bottom - box_h
	var box_left := -box_w / 2.0
	_bubble.offset_left = box_left
	_bubble.offset_top = box_top
	_bubble.offset_right = box_left + box_w
	_bubble.offset_bottom = box_bottom
	_speech_label.offset_left = box_left + BUBBLE_PAD_X
	_speech_label.offset_top = box_top + BUBBLE_PAD_Y
	_speech_label.offset_right = box_left + box_w - BUBBLE_PAD_X
	_speech_label.offset_bottom = box_bottom - BUBBLE_PAD_Y
	_tail.polygon = PackedVector2Array([
		Vector2(-TAIL_HALF_WIDTH, box_bottom + 1.0),
		Vector2(TAIL_HALF_WIDTH, box_bottom + 1.0),
		Vector2(0.0, 0.0),
	])


func _place(snap: bool) -> void:
	if snap or not _has_server_position:
		position = server_position + visual_offset
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
				_speech.modulate.a = 1.0
	if not _has_server_position:
		return
	var goal := server_position + visual_offset
	position = position.lerp(goal, clampf(lerp_speed * delta, 0.0, 1.0))
