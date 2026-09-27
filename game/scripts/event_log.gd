extends RichTextLabel

const MAX_EVENTS := 20

var _lines: Array[String] = []


func clear_events() -> void:
	_lines.clear()
	text = ""


func add_event(line: String) -> void:
	_lines.append(line)
	while _lines.size() > MAX_EVENTS:
		_lines.remove_at(0)
	text = "\n".join(_lines)
	call_deferred("_follow_bottom")


func _follow_bottom() -> void:
	scroll_to_line(get_line_count())
