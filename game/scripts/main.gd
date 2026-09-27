extends Node

@onready var _network: Node = $NetworkClient
@onready var _world: Node2D = $World
@onready var _hud: CanvasLayer = $HUD


func _ready() -> void:
	_network.snapshot_received.connect(_on_snapshot)
	_network.agent_updated.connect(_on_agent_update)
	_network.event_received.connect(_on_event)
	_network.connection_changed.connect(_on_connection)


func _on_snapshot(data: Dictionary) -> void:
	_world.apply_snapshot(data)
	_hud.apply_snapshot(data)


func _on_agent_update(data: Dictionary) -> void:
	_world.apply_agent_update(data)
	_hud.apply_agent_update(data)


func _on_event(data: Dictionary) -> void:
	_hud.apply_event(data)
	if str(data.get("event", "")) != "said":
		return
	if _world.has_method("show_speech"):
		_world.show_speech(str(data.get("agent_id", "")), str(data.get("content", "")))


func _on_connection(online: bool) -> void:
	_hud.set_connection(online)
