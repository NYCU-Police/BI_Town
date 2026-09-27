extends RichTextLabel

const MAX_EVENTS := 20

var _lines: Array[String] = []


func clear_events() -> void:
	_lines.clear()
	text = ""


func add_event(line: String, muted: bool = false) -> void:
	var shown := line
	if muted:
		shown = "[color=#9a9a94]%s[/color]" % line
	_lines.push_front(shown)
	if _lines.size() > MAX_EVENTS:
		_lines.resize(MAX_EVENTS)
	text = "\n".join(_lines)
