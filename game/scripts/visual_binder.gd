class_name VisualBinder
extends RefCounted

## Appearance only. Paths are a convention, not stored in the manifest.
const _MANIFEST_PATH := "res://data/visual_manifest.json"
const _USER_PATH := "res://assets/packs/user/%s/%s.png"
const _DEFAULT_PATH := "res://assets/packs/default/%s/%s.png"

static var _content: Dictionary = {}
static var _loaded := false
static var _warned: Dictionary = {}
static var _logged: Dictionary = {}


static func apply(sprite: Sprite2D, host: Node, content_id: String) -> void:
	var resolved := _resolve(content_id)
	var previous := host.get_node_or_null("Fallback")
	if resolved.is_empty():
		_show_placeholder(sprite, host, content_id, previous)
		return
	var texture := load(resolved) as Texture2D
	if texture == null:
		_warn_once(content_id, "could not load %s, using placeholder" % resolved)
		_show_placeholder(sprite, host, content_id, previous)
		return
	sprite.texture = texture
	sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sprite.centered = true
	sprite.visible = true
	var size := texture.get_size()
	var origin := _origin(content_id)
	sprite.offset = Vector2((0.5 - origin.x) * size.x, (0.5 - origin.y) * size.y)
	if previous != null:
		previous.queue_free()
	_log_once(content_id, resolved)


static func apply_icon(host: Control, content_id: String) -> void:
	var resolved := _resolve(content_id)
	var existing_icon := host.get_node_or_null("Icon")
	var existing_block := host.get_node_or_null("Fallback")
	if resolved.is_empty():
		if existing_icon != null:
			existing_icon.queue_free()
		_show_control_placeholder(host, content_id, existing_block)
		return
	var texture := load(resolved) as Texture2D
	if texture == null:
		_warn_once(content_id, "could not load %s, using placeholder" % resolved)
		if existing_icon != null:
			existing_icon.queue_free()
		_show_control_placeholder(host, content_id, existing_block)
		return
	var icon := existing_icon as TextureRect
	if icon == null:
		if existing_icon != null:
			existing_icon.queue_free()
		icon = TextureRect.new()
		icon.name = "Icon"
		icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		icon.custom_minimum_size = Vector2(16, 16)
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		host.add_child(icon)
	icon.texture = texture
	if existing_block != null:
		existing_block.queue_free()
	_log_once(content_id, resolved)


static func name_color(content_id: String) -> Color:
	_ensure()
	var entry := _entry(_lookup_key(content_id))
	var hex := str(entry.get("name_color", "#ededed"))
	if not hex.is_valid_html_color():
		return Color(0.93, 0.93, 0.93)
	return Color.html(hex)


static func _resolve(content_id: String) -> String:
	_ensure()
	var entry := _entry(_lookup_key(content_id))
	if entry.is_empty():
		_warn_once(content_id, "missing manifest entry, using placeholder")
		return ""
	var category := str(entry.get("category", ""))
	var file_name := _file_name(content_id)
	if category.is_empty() or file_name.is_empty():
		_warn_once(content_id, "incomplete manifest entry, using placeholder")
		return ""
	var user_path := _USER_PATH % [category, file_name]
	if ResourceLoader.exists(user_path):
		return user_path
	var default_path := _DEFAULT_PATH % [category, file_name]
	if ResourceLoader.exists(default_path):
		return default_path
	_warn_once(content_id, "fell back to placeholder")
	return ""


static func _show_placeholder(
	sprite: Sprite2D,
	host: Node,
	content_id: String,
	previous: Node,
) -> void:
	sprite.texture = null
	sprite.visible = false
	if previous != null:
		previous.queue_free()
	var box := _footprint(content_id)
	var origin := _origin(content_id)
	var fallback := Node2D.new()
	fallback.name = "Fallback"
	var rect := ColorRect.new()
	rect.color = _placeholder_color(content_id)
	rect.size = box
	rect.position = Vector2(-origin.x * box.x, -origin.y * box.y)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var label := Label.new()
	label.text = content_id
	label.position = Vector2(rect.position.x, rect.position.y - 14.0)
	label.size = Vector2(maxf(box.x, 48.0), 14.0)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", 8)
	label.add_theme_color_override("font_color", Color.WHITE)
	fallback.add_child(rect)
	fallback.add_child(label)
	host.add_child(fallback)


static func _show_control_placeholder(host: Control, content_id: String, previous: Node) -> void:
	if previous != null:
		previous.queue_free()
	var box := _footprint(content_id)
	var fallback := ColorRect.new()
	fallback.name = "Fallback"
	fallback.color = _placeholder_color(content_id)
	fallback.custom_minimum_size = Vector2(16, 16)
	fallback.size = Vector2(16, 16)
	fallback.mouse_filter = Control.MOUSE_FILTER_IGNORE
	host.add_child(fallback)


static func _lookup_key(content_id: String) -> String:
	if content_id.begins_with("agent.player_"):
		return "agent.player"
	return content_id


static func _file_name(content_id: String) -> String:
	var key := _lookup_key(content_id)
	var dot := key.find(".")
	if dot < 0:
		return key
	return key.substr(dot + 1)


static func _entry(key: String) -> Dictionary:
	var raw: Variant = _content.get(key, {})
	if typeof(raw) != TYPE_DICTIONARY:
		return {}
	return raw


static func _origin(content_id: String) -> Vector2:
	var raw: Variant = _entry(_lookup_key(content_id)).get("origin", [0.5, 1.0])
	if typeof(raw) != TYPE_ARRAY or raw.size() < 2:
		return Vector2(0.5, 1.0)
	return Vector2(float(raw[0]), float(raw[1]))


static func _footprint(content_id: String) -> Vector2:
	var raw: Variant = _entry(_lookup_key(content_id)).get("footprint", [16, 16])
	if typeof(raw) != TYPE_ARRAY or raw.size() < 2:
		return Vector2(16, 16)
	return Vector2(float(raw[0]), float(raw[1]))


static func _placeholder_color(content_id: String) -> Color:
	var hex := str(_entry(_lookup_key(content_id)).get("placeholder_color", "#b87a47"))
	if not hex.is_valid_html_color():
		return Color(0.72, 0.48, 0.28)
	return Color.html(hex)


static func _warn_once(content_id: String, detail: String) -> void:
	if _warned.has(content_id):
		return
	_warned[content_id] = true
	push_warning("VisualBinder %s %s" % [content_id, detail])


static func _log_once(content_id: String, path: String) -> void:
	if _logged.has(content_id):
		return
	_logged[content_id] = true
	print("VisualBinder %s loaded %s" % [content_id, path])


static func _ensure() -> void:
	if _loaded:
		return
	_loaded = true
	if not FileAccess.file_exists(_MANIFEST_PATH):
		push_error("visual manifest is missing: %s" % _MANIFEST_PATH)
		return
	var text := FileAccess.get_file_as_string(_MANIFEST_PATH)
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("visual manifest is not an object: %s" % _MANIFEST_PATH)
		return
	_content = parsed
