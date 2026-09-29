extends RefCounted

const BY_ID := {
	"mina_home": "Mina 的家",
	"alex_home": "Alex 的家",
	"rin_home": "Rin 的家",
	"cafe": "咖啡廳",
	"store": "便利商店",
	"office": "辦公室",
	"library": "圖書館",
	"plaza": "廣場",
	"park": "公園",
}


static func label(poi_id: String) -> String:
	return str(BY_ID.get(poi_id, poi_id))
