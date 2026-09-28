shader_type canvas_item;

// Brightness only. Shifting UV would sample neighboring atlas tiles.
uniform float speed = 1.4;

void fragment() {
	vec4 tex = texture(TEXTURE, UV);
	float wave = sin(TIME * speed + UV.x * 48.0 + UV.y * 22.0);
	float crest = sin(TIME * speed * 0.7 + UV.y * 36.0 - UV.x * 12.0);
	float glow = 0.92 + wave * 0.06 + crest * 0.04;
	COLOR = vec4(tex.rgb * glow + vec3(0.0, 0.04, 0.06) * max(wave, 0.0), tex.a);
}
