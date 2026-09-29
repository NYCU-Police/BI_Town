extends Node

@onready var _network: Node = $NetworkClient
@onready var _world: Node2D = $World
@onready var _hud: CanvasLayer = $HUD


func _ready() -> void:
	_network.snapshot_received.connect(_on_snapshot)
	_network.agent_updated.connect(_on_agent_update)
	_network.event_received.connect(_on_event)
	_network.connection_changed.connect(_on_connection)
	if _network.has_signal("notebook_received"):
		_network.notebook_received.connect(_on_notebook)
	if _network.has_signal("assembly_received"):
		_network.assembly_received.connect(_on_assembly)
	if _network.has_signal("reveal_received"):
		_network.reveal_received.connect(_on_reveal)
	if _network.has_signal("round_started"):
		_network.round_started.connect(_on_round_started)


func _on_snapshot(data: Dictionary) -> void:
	_world.apply_snapshot(data)
	_hud.apply_snapshot(data)


func _on_agent_update(data: Dictionary) -> void:
	_world.apply_agent_update(data)
	_hud.apply_agent_update(data)


func _on_assembly(message: Dictionary) -> void:
	if _hud.has_method("show_assembly"):
		_hud.show_assembly(message)


func _on_reveal(message: Dictionary) -> void:
	if _hud.has_method("show_reveal"):
		_hud.show_reveal(message)


func _on_round_started(message: Dictionary) -> void:
	if _hud.has_method("hide_assembly"):
		_hud.hide_assembly()
	if _hud.has_method("set_notice"):
		_hud.set_notice(str(message.get("notice", "")))
	if _world.has_method("set_notice"):
		_world.set_notice(str(message.get("notice", "")))


func _on_notebook(message: Dictionary) -> void:
	if _hud.has_method("set_notes"):
		_hud.set_notes(message.get("notes", []), message.get("note_ids", []))
	if _world.has_method("set_notice"):
		_world.set_notice(str(message.get("notice", "")))


func _on_event(data: Dictionary) -> void:
	_hud.apply_event(data)
	if _world.has_method("present_event"):
		_world.present_event(data)
	var audio := get_node_or_null("GameAudio")
	if audio != null and audio.has_method("present_event"):
		audio.present_event(data)
	if str(data.get("event", "")) == "conversing" or str(data.get("event", "")) == "conversing_ended":
		if _world.has_method("show_conversing"):
			_world.show_conversing(
				str(data.get("agent_id", "")),
				str(data.get("target_agent_id", "")),
				str(data.get("event", "")) == "conversing",
			)
		return
	if str(data.get("event", "")) != "said":
		return
	if _world.has_method("show_speech"):
		_world.show_speech(str(data.get("agent_id", "")), str(data.get("content", "")))


func _on_connection(online: bool) -> void:
	_hud.set_connection(online)
