extends CanvasModulate

## Presentation tint from the server clock. Does not advance time.
const _COLORS: Array = [
	[0, Color(0.18, 0.24, 0.52)],
	[5 * 60, Color(0.18, 0.24, 0.52)],
	[6 * 60 + 30, Color(1.0, 0.78, 0.62)],
	[8 * 60, Color(1.0, 0.96, 0.90)],
	[10 * 60, Color(1, 1, 1)],
	[16 * 60, Color(1, 1, 1)],
	[17 * 60 + 30, Color(1.0, 0.64, 0.40)],
	[19 * 60 + 30, Color(0.16, 0.22, 0.50)],
	[24 * 60, Color(0.16, 0.22, 0.50)],
]
const _NIGHT: Array = [
	[0, 1.0],
	[5 * 60, 1.0],
	[7 * 60, 0.2],
	[8 * 60, 0.0],
	[17 * 60, 0.0],
	[18 * 60, 0.55],
	[19 * 60 + 30, 1.0],
	[24 * 60, 1.0],
]

var _target := Color(1.0, 0.96, 0.90)
var _night_target := 0.0
var _night := 0.0


func _ready() -> void:
	color = _target


func set_clock(time_text: String) -> void:
	var minutes := _minutes(time_text)
	if minutes < 0:
		return
	_target = _sample_color(minutes)
	_night_target = _sample_night(minutes)


func _process(delta: float) -> void:
	var blend := clampf(delta * 1.6, 0.0, 1.0)
	color = color.lerp(_target, blend)
	_night = lerpf(_night, _night_target, blend)
	for node in get_tree().get_nodes_in_group("night_light"):
		if node is PointLight2D:
			(node as PointLight2D).energy = _night * 1.15


func _minutes(time_text: String) -> int:
	var parts := time_text.split(":")
	if parts.size() < 2 or not parts[0].is_valid_int() or not parts[1].is_valid_int():
		return -1
	return int(parts[0]) * 60 + int(parts[1])


func _sample_color(minutes: int) -> Color:
	var previous: Array = _COLORS[0]
	for stop in _COLORS:
		var at := int(stop[0])
		if minutes < at:
			var span := float(at - int(previous[0]))
			var weight := 0.0 if span <= 0.0 else float(minutes - int(previous[0])) / span
			return (previous[1] as Color).lerp(stop[1] as Color, weight)
		previous = stop
	return previous[1] as Color


func _sample_night(minutes: int) -> float:
	var previous: Array = _NIGHT[0]
	for stop in _NIGHT:
		var at := int(stop[0])
		if minutes < at:
			var span := float(at - int(previous[0]))
			var weight := 0.0 if span <= 0.0 else float(minutes - int(previous[0])) / span
			return lerpf(float(previous[1]), float(stop[1]), weight)
		previous = stop
	return float(previous[1])
