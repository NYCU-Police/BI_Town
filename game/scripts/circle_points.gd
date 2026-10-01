extends RefCounted


static func points(radius: float, count: int) -> PackedVector2Array:
	var drawn := PackedVector2Array()
	for index in count:
		var angle := TAU * float(index) / float(count)
		drawn.append(Vector2(cos(angle), sin(angle)) * radius)
	return drawn
