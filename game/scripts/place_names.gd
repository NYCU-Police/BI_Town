extends RefCounted

const _Rules := preload("res://scripts/game_config.gd")


static func label(poi_id: String) -> String:
	return _Rules.place_label(poi_id)
