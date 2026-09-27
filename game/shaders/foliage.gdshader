shader_type canvas_item;

// Kenney grass and pines are mint. Shift only pixels where green leads,
// and leave blue water, roads, and trunks alone.
void fragment() {
	vec4 color = texture(TEXTURE, UV);
	float teal = smoothstep(0.10, 0.40, color.g - color.r)
		* smoothstep(0.05, 0.35, color.b - color.r)
		* smoothstep(0.02, 0.14, color.g - color.b);
	float shade = dot(color.rgb, vec3(0.25, 0.55, 0.20));
	vec3 grass = vec3(0.40, 0.58, 0.16) * (0.50 + shade);
	COLOR = vec4(mix(color.rgb, grass, teal), color.a);
}
