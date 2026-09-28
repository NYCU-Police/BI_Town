class_name VisualBinder
extends RefCounted

## Maps a content id to a sprite. Missing art becomes a ColorRect plus the id.
const _MANIFEST_PATH := "res://data/visual_manifest.json"

static var _content: Dictionary = {}
static var _loaded := false


static func apply(sprite: Sprite2D, host: Node2D, content_id: String) -> void:
	var path := art_path(content_id)
	var previous := host.get_node_or_null("Fallback")
	if path != "" and ResourceLoader.exists(path):
		sprite.texture = load(path) as Texture2D
		sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		sprite.visible = true
		if previous != null:
			previous.queue_free()
		return
	sprite.texture = null
	sprite.visible = false
	if previous != null:
		previous.queue_free()
	var fallback := Node2D.new()
	fallback.name = "Fallback"
	var rect := ColorRect.new()
	rect.color = Color(0.72, 0.48, 0.28)
	rect.size = Vector2(16, 16)
	rect.position = Vector2(-8, -16)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var label := Label.new()
	label.text = content_id
	label.position = Vector2(-24, -30)
	label.size = Vector2(48, 12)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", 8)
	label.add_theme_color_override("font_color", Color.WHITE)
	fallback.add_child(rect)
	fallback.add_child(label)
	host.add_child(fallback)


static func art_path(content_id: String) -> String:
	_ensure()
	var key := "player" if content_id.begins_with("player_") else content_id
	var entry: Variant = _content.get(key, {})
	if typeof(entry) != TYPE_DICTIONARY:
		return ""
	return str((entry as Dictionary).get("art", ""))


static func _ensure() -> void:
	if _loaded:
		return
	_loaded = true
	if not ResourceLoader.exists(_MANIFEST_PATH):
		return
	var text := FileAccess.get_file_as_string(_MANIFEST_PATH)
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var content: Variant = (parsed as Dictionary).get("content", {})
	if typeof(content) == TYPE_DICTIONARY:
		_content = content
