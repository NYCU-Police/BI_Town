extends Node2D

@export var lerp_speed: float = 8.0

const COLORS := {
	"mina": Color(0.91, 0.45, 0.48),
	"alex": Color(0.35, 0.72, 0.78),
}

var target_position: Vector2 = Vector2.ZERO
var _has_server_position: bool = false

@onready var _body: ColorRect = $Body
@onready var _label: Label = $Label


func update_from_server(data: Dictionary, snap: bool = false) -> void:
	var pos: Variant = data.get("position", {})
	if typeof(pos) != TYPE_DICTIONARY:
		push_error("NPC update missing position: %s" % str(data))
		return

	var coords: Dictionary = pos
	target_position = Vector2(float(coords.get("x", 0.0)), float(coords.get("y", 0.0)))

	var agent_name := str(data.get("name", data.get("id", "NPC")))
	var agent_state := str(data.get("state", ""))
	_label.text = "%s (%s)" % [agent_name, agent_state]

	var agent_id := str(data.get("id", ""))
	if COLORS.has(agent_id):
		_body.color = COLORS[agent_id]

	if snap or not _has_server_position:
		position = target_position
		_has_server_position = true


func _process(delta: float) -> void:
	if not _has_server_position:
		return
	position = position.lerp(target_position, clampf(lerp_speed * delta, 0.0, 1.0))
