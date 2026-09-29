extends Camera2D

## Follows the local player at a zoom that makes a 16px sprite readable
## on a 1280×720 window. Drag to look around; space snaps back.

const MAP := Vector2(576, 448)
const HUD_WIDTH := 0.0
const MIN_ZOOM := 1
const MAX_ZOOM := 4
const DEFAULT_ZOOM := 3
const DRAG_THRESHOLD := 6.0

var _zoom_level := DEFAULT_ZOOM
var _following := true
var _dragging := false
var _drag_moved := false
var _press_pos := Vector2.ZERO
var _tween: Tween


func _ready() -> void:
	add_to_group("town_camera")
	texture_filter = TEXTURE_FILTER_NEAREST
	var viewport := get_viewport()
	if viewport != null:
		viewport.canvas_item_default_texture_filter = (
			Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
		)
	zoom = Vector2(float(DEFAULT_ZOOM), float(DEFAULT_ZOOM))
	_zoom_level = DEFAULT_ZOOM
	var world := get_parent()
	if world != null and world.get("POIS") is Dictionary:
		var pois: Dictionary = world.POIS
		if pois.has("plaza"):
			position = _frame_on_player(pois["plaza"])


func _process(_delta: float) -> void:
	if not _following:
		return
	var spot := _player_spot()
	if spot == Vector2.INF:
		return
	position = _clamp_position(_frame_on_player(spot))


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key := event as InputEventKey
		if key.pressed and not key.echo and key.keycode == KEY_SPACE:
			_following = true
			_dragging = false
			_stop_tween()
			return
	if event is InputEventMouseButton:
		var button := event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_LEFT:
			if button.pressed and _over_hud(button.position):
				return
			if button.pressed:
				_dragging = true
				_drag_moved = false
				_press_pos = button.position
				_stop_tween()
			else:
				_dragging = false
		elif button.pressed and (
			button.button_index == MOUSE_BUTTON_WHEEL_UP
			or button.button_index == MOUSE_BUTTON_WHEEL_DOWN
		):
			if _over_hud(button.position):
				return
			var step := 1 if button.button_index == MOUSE_BUTTON_WHEEL_UP else -1
			_zoom_at(button.position, _zoom_level + step)
	elif event is InputEventMouseMotion and _dragging:
		var motion := event as InputEventMouseMotion
		if not _drag_moved and motion.position.distance_to(_press_pos) < DRAG_THRESHOLD:
			return
		_drag_moved = true
		_following = false
		position -= motion.relative / zoom
		position = _clamp_position(position)


func focus_agent(agent_id: String) -> void:
	var world := get_parent()
	if world == null or not world.has_method("npc_position"):
		return
	var spot: Vector2 = world.npc_position(agent_id)
	if spot == Vector2.INF:
		return
	_following = false
	_stop_tween()
	_tween = create_tween()
	_tween.tween_property(
		self,
		"position",
		_clamp_position(_frame_on_player(spot)),
		0.45,
	).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


func _player_spot() -> Vector2:
	var world := get_parent()
	if world == null or not world.has_method("local_player_position"):
		return Vector2.INF
	return world.local_player_position()


func _zoom_at(screen_at: Vector2, next_level: int) -> void:
	var level := clampi(next_level, MIN_ZOOM, MAX_ZOOM)
	if level == _zoom_level:
		return
	_stop_tween()
	var before := zoom
	var world_at := get_screen_center_position() + (screen_at - get_viewport_rect().size / 2.0) / before
	_zoom_level = level
	zoom = Vector2(float(level), float(level))
	if _following:
		var spot := _player_spot()
		if spot != Vector2.INF:
			position = _clamp_position(_frame_on_player(spot))
			return
	var after_screen := (world_at - position) * zoom + get_viewport_rect().size / 2.0
	position += (after_screen - screen_at) / zoom
	position = _clamp_position(position)


func _frame_on_player(world_pos: Vector2) -> Vector2:
	var view_px := get_viewport_rect().size
	var play_center := Vector2((view_px.x - HUD_WIDTH) * 0.5, view_px.y * 0.5)
	var delta_px := play_center - view_px * 0.5
	return world_pos - delta_px / zoom


func _clamp_position(pos: Vector2) -> Vector2:
	var view := get_viewport_rect().size / zoom
	if view.x >= MAP.x and view.y >= MAP.y:
		return pos
	var half := view / 2.0
	var min_x := half.x
	var max_x := MAP.x - half.x + HUD_WIDTH / zoom.x
	if min_x > max_x:
		pos.x = MAP.x / 2.0
	else:
		pos.x = clampf(pos.x, min_x, max_x)
	var min_y := half.y
	var max_y := MAP.y - half.y
	if min_y > max_y:
		pos.y = MAP.y / 2.0
	else:
		pos.y = clampf(pos.y, min_y, max_y)
	return pos


func _over_hud(screen_at: Vector2) -> bool:
	return screen_at.x >= get_viewport_rect().size.x - HUD_WIDTH


func _stop_tween() -> void:
	if _tween != null and _tween.is_valid():
		_tween.kill()
	_tween = null
