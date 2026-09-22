extends RichTextLabel

const MAX_EVENTS := 20

var _lines: Array[String] = []


func clear_events() -> void:
	_lines.clear()
	text = ""


func add_event(line: String) -> void:
	_lines.push_front(line)
	if _lines.size() > MAX_EVENTS:
		_lines.resize(MAX_EVENTS)
	text = "\n".join(_lines)
