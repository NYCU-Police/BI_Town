extends Node2D

@export var lerp_speed: float = 8.0

const COLORS := {
	"mina": Color(0.91, 0.45, 0.48),
	"alex": Color(0.35, 0.72, 0.78),
	"rin": Color(0.95, 0.78, 0.35),
}
const SPEECH_SECONDS := 5.0
const LABEL_TOP := -32.0
const LABEL_BOTTOM := -12.0
const SPEECH_TOP := -78.0
const SPEECH_BOTTOM := -36.0
const STACK_LIFT := 22.0
const BODY_STEP := 26.0

var server_position: Vector2 = Vector2.ZERO
var visual_offset: Vector2 = Vector2.ZERO
var _has_server_position: bool = false
var _speech_left: float = 0.0

@onready var _body: ColorRect = $Body
@onready var _label: Label = $Label
@onready var _speech: Label = $Speech


func server_anchor() -> Vector2:
	return server_position


func update_from_server(data: Dictionary, snap: bool = false) -> void:
	var pos: Variant = data.get("position", {})
	if typeof(pos) != TYPE_DICTIONARY:
		push_error("NPC update missing position: %s" % str(data))
		return

	var coords: Dictionary = pos
	server_position = Vector2(float(coords.get("x", 0.0)), float(coords.get("y", 0.0)))

	var agent_name := str(data.get("name", data.get("id", "NPC")))
	var agent_state := str(data.get("state", ""))
	_label.text = "%s (%s)" % [agent_name, agent_state]

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
	_speech.offset_top = SPEECH_TOP - lift
	_speech.offset_bottom = SPEECH_BOTTOM - lift
	_place(snap)


func show_speech(content: String) -> void:
	var utterance := content.strip_edges()
	if utterance.is_empty():
		return
	_speech.text = utterance
	_speech.visible = true
	_speech_left = SPEECH_SECONDS


func _place(snap: bool) -> void:
	if snap or not _has_server_position:
		position = server_position + visual_offset
		_has_server_position = true


func _process(delta: float) -> void:
	if _speech_left > 0.0:
		_speech_left -= delta
		if _speech_left <= 0.0:
			_speech.visible = false
			_speech.text = ""
	if not _has_server_position:
		return
	var goal := server_position + visual_offset
	position = position.lerp(goal, clampf(lerp_speed * delta, 0.0, 1.0))
