extends RichTextLabel

const MAX_EVENTS := 20

var _entries: Array[Dictionary] = []
var _show_movement := false


func clear_events() -> void:
	_entries.clear()
	text = ""


func add_event(line: String, category: String = "talk") -> void:
	_entries.append({"line": line, "category": category})
	while _entries.size() > MAX_EVENTS:
		_entries.remove_at(0)
	_render()


func set_movement_visible(show: bool) -> void:
	_show_movement = show
	_render()


func _render() -> void:
	var lines: PackedStringArray = PackedStringArray()
	for entry in _entries:
		if str(entry.get("category", "")) == "move" and not _show_movement:
			continue
		lines.append(str(entry.get("line", "")))
	text = "\n".join(lines)
	call_deferred("_follow_bottom")


func _follow_bottom() -> void:
	scroll_to_line(get_line_count())
