extends Camera2D

## Integer zoom keeps Kenney pixels on the nearest filter. Drag pans.
## The opening frame shows the whole 60×40 map beside the event panel.

const MAP := Vector2(960, 640)
const HUD_WIDTH := 360.0
const MIN_ZOOM := 1
const MAX_ZOOM := 4

var _zoom_level := 1
var _dragging := false
var _tween: Tween


func _ready() -> void:
	add_to_group("town_camera")
	texture_filter = TEXTURE_FILTER_NEAREST
	var viewport := get_viewport()
	if viewport != null:
		viewport.canvas_item_default_texture_filter = (
			Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
		)
	_zoom_level = MIN_ZOOM
	zoom = Vector2.ONE
	_fit_whole_map()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var button := event as InputEventMouseButton
		if button.button_index == MOUSE_BUTTON_LEFT:
			if button.pressed and _over_hud(button.position):
				return
			_dragging = button.pressed
			if button.pressed:
				_stop_tween()
		elif button.pressed and (
			button.button_index == MOUSE_BUTTON_WHEEL_UP
			or button.button_index == MOUSE_BUTTON_WHEEL_DOWN
		):
			var step := -1 if button.button_index == MOUSE_BUTTON_WHEEL_UP else 1
			_zoom_at(button.position, _zoom_level + step)
	elif event is InputEventMouseMotion and _dragging:
		var motion := event as InputEventMouseMotion
		position -= motion.relative / zoom


func focus_agent(agent_id: String) -> void:
	var world := get_parent()
	if world == null or not world.has_method("npc_position"):
		return
	var spot: Vector2 = world.npc_position(agent_id)
	if spot == Vector2.INF:
		return
	_stop_tween()
	_tween = create_tween()
	_tween.tween_property(
		self,
		"position",
		_clamp_position(_frame_point(spot)),
		0.45,
	).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)


func _fit_whole_map() -> void:
	var view := get_viewport_rect().size
	var spare_x := (view.x - HUD_WIDTH) - MAP.x
	var left := spare_x / 2.0 if spare_x > 0.0 else 8.0
	var spare_y := view.y - MAP.y
	var top := spare_y / 2.0 if spare_y > 0.0 else 8.0
	position = Vector2(view.x / 2.0 - left, view.y / 2.0 - top)


func _zoom_at(screen_at: Vector2, next_level: int) -> void:
	var level := clampi(next_level, MIN_ZOOM, MAX_ZOOM)
	if level == _zoom_level:
		return
	_stop_tween()
	var before := zoom
	var world_at := get_screen_center_position() + (screen_at - get_viewport_rect().size / 2.0) / before
	_zoom_level = level
	zoom = Vector2(float(level), float(level))
	var after_screen := (world_at - position) * zoom + get_viewport_rect().size / 2.0
	position += (after_screen - screen_at) / zoom
	position = _clamp_position(position)


func _frame_point(world_pos: Vector2) -> Vector2:
	var view := get_viewport_rect().size / zoom
	var visible_center_x := (view.x - HUD_WIDTH / zoom.x) / 2.0
	return Vector2(
		world_pos.x - (visible_center_x - view.x / 2.0) / zoom.x,
		world_pos.y,
	)


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
