extends Node

## Presentation only. Nothing plays until the first click, so the browser
## autoplay rule is satisfied. Volumes stay low.

const _MUSIC := "res://assets/packs/default/audio/village.ogg"
const _CLICK := "res://assets/packs/default/audio/click.wav"
const _PICKUP := "res://assets/packs/default/audio/pickup.wav"
const _EAT := "res://assets/packs/default/audio/eat.wav"
const _GIVE := "res://assets/packs/default/audio/give.wav"
const _MUSIC_DB := -18.0
const _SFX_DB := -14.0

var _unlocked := false
var _muted := false
var _music: AudioStreamPlayer
var _sfx: Array[AudioStreamPlayer] = []
var _sfx_cursor := 0


func _ready() -> void:
	_music = AudioStreamPlayer.new()
	_music.name = "Music"
	_music.volume_db = _MUSIC_DB
	_music.bus = "Master"
	var stream := load(_MUSIC)
	if stream is AudioStreamOggVorbis:
		var looped := (stream as AudioStreamOggVorbis).duplicate() as AudioStreamOggVorbis
		looped.loop = true
		_music.stream = looped
	else:
		_music.stream = stream
	add_child(_music)
	for index in 3:
		var player := AudioStreamPlayer.new()
		player.name = "Sfx%d" % index
		player.volume_db = _SFX_DB
		add_child(player)
		_sfx.append(player)


func _input(event: InputEvent) -> void:
	if _unlocked:
		return
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		unlock()


func unlock() -> void:
	if _unlocked:
		return
	_unlocked = true
	if not _muted and _music.stream != null:
		_music.play()


func is_muted() -> bool:
	return _muted


func set_muted(muted: bool) -> void:
	_muted = muted
	AudioServer.set_bus_mute(AudioServer.get_bus_index("Master"), muted)
	if not muted:
		unlock()


func play_click() -> void:
	unlock()
	_play(_CLICK)


func present_event(data: Dictionary) -> void:
	match str(data.get("event", "")):
		"picked_up":
			_play(_PICKUP)
		"ate":
			_play(_EAT)
		"gave":
			_play(_GIVE)


func _play(path: String) -> void:
	if not _unlocked or _muted or _sfx.is_empty():
		return
	var stream := load(path)
	if stream == null:
		return
	var player := _sfx[_sfx_cursor % _sfx.size()]
	_sfx_cursor += 1
	player.stream = stream
	player.play()
