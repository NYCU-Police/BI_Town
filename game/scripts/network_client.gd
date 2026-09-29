extends Node

signal snapshot_received(data: Dictionary)
signal agent_updated(data: Dictionary)
signal event_received(data: Dictionary)
signal connection_changed(online: bool)
signal intent_resolved(client_seq: int, ok: bool, reason: String)
signal dialogue_received(data: Dictionary)
signal notebook_received(message: Dictionary)
signal assembly_received(message: Dictionary)
signal reveal_received(message: Dictionary)
signal round_started(message: Dictionary)

## Desktop default. Web builds resolve the URL in _ready().
@export var websocket_url: String = "ws://127.0.0.1:8000/ws"

const RECONNECT_INITIAL_SECONDS := 2.0
const RECONNECT_MAX_SECONDS := 30.0

var _socket: WebSocketPeer
var _resolved_url: String = ""
var _reconnect_delay: float = RECONNECT_INITIAL_SECONDS
var _reconnect_timer: float = 0.0
var _online: bool = false
var _client_seq: int = 0
var _player_token: String = ""
const _TOKEN_KEY := "bi_town_player_token"


func _ready() -> void:
	_player_token = _load_token()
	_resolved_url = _with_token(_resolve_websocket_url(), _player_token)
	print("WebSocket URL: ", _resolved_url)
	_connect_now()


func _process(delta: float) -> void:
	if _socket == null:
		_reconnect_timer -= delta
		if _reconnect_timer <= 0.0:
			_connect_now()
		return

	_socket.poll()
	match _socket.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if not _online:
				_reconnect_delay = RECONNECT_INITIAL_SECONDS
				_set_online(true)
			_read_messages()
		WebSocketPeer.STATE_CLOSED:
			_handle_closed()


func _resolve_websocket_url() -> String:
	if not OS.has_feature("web"):
		return websocket_url

	var override_url := _websocket_url_from_query()
	if not override_url.is_empty():
		return override_url

	var location: Variant = JavaScriptBridge.get_interface("location")
	if location == null:
		push_error("JavaScriptBridge location unavailable; using desktop WebSocket URL")
		return websocket_url

	# Same host + port as the page. Docker (:8100) and production Caddy
	# both serve / , /api , /ws from one origin — do not special-case localhost
	# to :8000 (that broke compose, where the published port is not 8000).
	# Split-server local dev (serve_web.py + uvicorn) still uses ?ws=.
	var page_protocol := str(location.protocol)
	var ws_protocol := "wss:" if page_protocol == "https:" else "ws:"
	return "%s//%s/ws" % [ws_protocol, str(location.host)]


func _websocket_url_from_query() -> String:
	var raw: Variant = JavaScriptBridge.eval(
		"decodeURIComponent(new URLSearchParams(window.location.search).get('ws') || '')"
	)
	if raw == null:
		return ""
	return str(raw).strip_edges()


func _connect_now() -> void:
	_socket = WebSocketPeer.new()
	var err := _socket.connect_to_url(_resolved_url)
	if err != OK:
		push_error("WebSocket connect_to_url failed (%s): %s" % [_resolved_url, error_string(err)])
		_socket = null
		_arm_reconnect()


func _read_messages() -> void:
	while _socket.get_available_packet_count() > 0:
		var text := _socket.get_packet().get_string_from_utf8()
		_handle_text(text)


func send_intent(intent: Dictionary) -> int:
	if _socket == null or _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		push_warning("WebSocket is not open; intent was not sent")
		return 0
	_client_seq += 1
	var payload: Dictionary = {
		"type": "intent",
		"client_seq": _client_seq,
		"intent": intent,
	}
	var err := _socket.send_text(JSON.stringify(payload))
	if err != OK:
		push_error("WebSocket send failed: %s" % error_string(err))
		return 0
	return _client_seq


func _handle_text(text: String) -> void:
	var trimmed := text.strip_edges()
	if not trimmed.begins_with("{"):
		return
	var parsed: Variant = JSON.parse_string(trimmed)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("WebSocket JSON parse failed: %s" % text)
		return

	var message: Dictionary = parsed
	var msg_type := str(message.get("type", ""))
	if msg_type == "intent_result":
		var reason: Variant = message.get("reason")
		intent_resolved.emit(
			int(message.get("client_seq", 0)),
			bool(message.get("ok", false)),
			"" if reason == null else str(reason),
		)
		return
	if msg_type == "session":
		_remember_token(str(message.get("player_token", "")))
		return
	if msg_type == "dialogue_result":
		dialogue_received.emit(message)
		return
	if msg_type == "notebook":
		notebook_received.emit(message)
		return
	if msg_type == "assembly_open":
		assembly_received.emit(message)
		return
	if msg_type == "reveal":
		reveal_received.emit(message)
		return
	if msg_type == "round_started":
		round_started.emit(message)
		return
	var raw_data: Variant = message.get("data", {})
	if typeof(raw_data) != TYPE_DICTIONARY:
		push_error("WebSocket message data is not an object: %s" % text)
		return

	var data: Dictionary = raw_data
	match msg_type:
		"world_snapshot":
			snapshot_received.emit(data)
		"agent_update":
			agent_updated.emit(data)
		"world_event":
			event_received.emit(data)
		_:
			push_error("Unknown WebSocket message type: %s" % msg_type)


func _handle_closed() -> void:
	var code := _socket.get_close_code()
	var reason := _socket.get_close_reason()
	push_warning("WebSocket closed (code=%s reason=%s)" % [code, reason])
	_socket = null
	_set_online(false)
	_arm_reconnect()


func _arm_reconnect() -> void:
	_reconnect_timer = _reconnect_delay
	push_warning("WebSocket reconnecting in %.0fs" % _reconnect_delay)
	_reconnect_delay = minf(_reconnect_delay * 2.0, RECONNECT_MAX_SECONDS)


func _set_online(value: bool) -> void:
	if _online == value:
		return
	_online = value
	connection_changed.emit(_online)


func _with_token(url: String, token: String) -> String:
	if token.is_empty():
		return url
	var joiner := "&" if url.contains("?") else "?"
	return "%s%splayer_token=%s" % [url, joiner, token.uri_encode()]


func _load_token() -> String:
	if OS.has_feature("web"):
		var raw: Variant = JavaScriptBridge.eval(
			"localStorage.getItem('%s') || ''" % _TOKEN_KEY
		)
		if raw == null:
			return ""
		return str(raw).strip_edges()
	var cfg := ConfigFile.new()
	if cfg.load("user://player_token.cfg") != OK:
		return ""
	return str(cfg.get_value("player", "token", "")).strip_edges()


func _remember_token(token: String) -> void:
	if token.is_empty() or token == _player_token:
		return
	_player_token = token
	if OS.has_feature("web"):
		JavaScriptBridge.eval(
			"localStorage.setItem('%s', %s)" % [_TOKEN_KEY, JSON.stringify(token)]
		)
	else:
		var cfg := ConfigFile.new()
		cfg.set_value("player", "token", token)
		cfg.save("user://player_token.cfg")
	_resolved_url = _with_token(_resolve_websocket_url(), token)
