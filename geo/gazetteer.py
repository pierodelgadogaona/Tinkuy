"""Nomenclátor local de respaldo.

Coordenadas aproximadas de centroides (distritos) o de la capital (regiones y
países). Se usan solo cuando el servicio de geocodificación no está disponible o
no encuentra el lugar, y siempre se marcan con su nivel de precisión real y como
«aproximadas». Nunca se usan para fingir precisión de calle o de edificio.
"""
from __future__ import annotations

# (nombre, [alias], tipo, lat, lon, contexto)
PLACES = [
    # --- Países (punto representativo: capital, salvo Perú: centroide) ---
    ("Perú", ["peru", "el perú"], "pais", -9.19, -75.02, ""),
    ("Argentina", [], "pais", -34.6037, -58.3816, "Buenos Aires"),
    ("Bolivia", [], "pais", -16.4897, -68.1193, "La Paz"),
    ("Brasil", ["brazil"], "pais", -15.7939, -47.8828, "Brasilia"),
    ("Chile", [], "pais", -33.4489, -70.6693, "Santiago"),
    ("Colombia", [], "pais", 4.7110, -74.0721, "Bogotá"),
    ("Ecuador", [], "pais", -0.1807, -78.4678, "Quito"),
    ("Venezuela", [], "pais", 10.4806, -66.9036, "Caracas"),
    ("Paraguay", [], "pais", -25.2637, -57.5759, "Asunción"),
    ("Uruguay", [], "pais", -34.9011, -56.1645, "Montevideo"),
    ("México", ["mexico"], "pais", 19.4326, -99.1332, "Ciudad de México"),
    ("Estados Unidos", ["ee. uu.", "ee.uu.", "eeuu", "usa"], "pais", 38.9072, -77.0369, "Washington D. C."),
    ("España", ["espana"], "pais", 40.4168, -3.7038, "Madrid"),
    ("Cuba", [], "pais", 23.1136, -82.3666, "La Habana"),
    ("Guatemala", [], "pais", 14.6349, -90.5069, "Ciudad de Guatemala"),
    ("Honduras", [], "pais", 14.0723, -87.1921, "Tegucigalpa"),
    ("El Salvador", [], "pais", 13.6929, -89.2182, "San Salvador"),
    ("Nicaragua", [], "pais", 12.1149, -86.2362, "Managua"),
    ("Costa Rica", [], "pais", 9.9281, -84.0907, "San José"),
    ("Panamá", ["panama"], "pais", 8.9824, -79.5199, "Ciudad de Panamá"),
    ("República Dominicana", [], "pais", 18.4861, -69.9312, "Santo Domingo"),
    ("Canadá", ["canada"], "pais", 45.4215, -75.6972, "Ottawa"),
    ("Francia", [], "pais", 48.8566, 2.3522, "París"),
    ("Italia", [], "pais", 41.9028, 12.4964, "Roma"),
    ("Alemania", [], "pais", 52.5200, 13.4050, "Berlín"),
    ("Reino Unido", [], "pais", 51.5074, -0.1278, "Londres"),
    ("Portugal", [], "pais", 38.7223, -9.1393, "Lisboa"),
    ("China", [], "pais", 39.9042, 116.4074, "Pekín"),
    ("Japón", ["japon"], "pais", 35.6762, 139.6503, "Tokio"),
    ("Rusia", [], "pais", 55.7558, 37.6173, "Moscú"),
    ("Ucrania", [], "pais", 50.4501, 30.5234, "Kiev"),
    ("Israel", [], "pais", 31.7683, 35.2137, "Jerusalén"),
    # --- Ciudades extranjeras frecuentes ---
    ("Buenos Aires", [], "ciudad", -34.6037, -58.3816, "Argentina"),
    ("Santiago de Chile", [], "ciudad", -33.4489, -70.6693, "Chile"),
    ("Bogotá", ["bogota"], "ciudad", 4.7110, -74.0721, "Colombia"),
    ("Quito", [], "ciudad", -0.1807, -78.4678, "Ecuador"),
    ("La Paz", [], "ciudad", -16.4897, -68.1193, "Bolivia"),
    ("Caracas", [], "ciudad", 10.4806, -66.9036, "Venezuela"),
    ("Ciudad de México", [], "ciudad", 19.4326, -99.1332, "México"),
    ("Madrid", [], "ciudad", 40.4168, -3.7038, "España"),
    ("Nueva York", ["new york"], "ciudad", 40.7128, -74.0060, "Estados Unidos"),
    ("Miami", [], "ciudad", 25.7617, -80.1918, "Estados Unidos"),
    ("Washington", [], "ciudad", 38.9072, -77.0369, "Estados Unidos"),
    # --- Regiones del Perú (punto: capital regional) ---
    ("Amazonas", [], "region", -6.2317, -77.8690, "Perú · capital: Chachapoyas"),
    ("Áncash", ["ancash"], "region", -9.5278, -77.5278, "Perú · capital: Huaraz"),
    ("Apurímac", ["apurimac"], "region", -13.6339, -72.8814, "Perú · capital: Abancay"),
    ("Ayacucho", [], "region", -13.1631, -74.2236, "Perú"),
    ("Cajamarca", [], "region", -7.1617, -78.5128, "Perú"),
    ("Cusco", ["cuzco"], "region", -13.5320, -71.9675, "Perú"),
    ("Huancavelica", [], "region", -12.7864, -74.9764, "Perú"),
    ("Huánuco", ["huanuco"], "region", -9.9306, -76.2422, "Perú"),
    ("Ica", [], "region", -14.0678, -75.7286, "Perú"),
    ("Junín", ["junin"], "region", -12.0651, -75.2049, "Perú · capital: Huancayo"),
    ("La Libertad", [], "region", -8.1116, -79.0288, "Perú · capital: Trujillo"),
    ("Lambayeque", [], "region", -6.7714, -79.8409, "Perú · capital: Chiclayo"),
    ("Loreto", [], "region", -3.7491, -73.2538, "Perú · capital: Iquitos"),
    ("Madre de Dios", [], "region", -12.5933, -69.1891, "Perú · capital: Puerto Maldonado"),
    ("Moquegua", [], "region", -17.1956, -70.9353, "Perú"),
    ("Pasco", ["cerro de pasco"], "region", -10.6864, -76.2625, "Perú · capital: Cerro de Pasco"),
    ("Piura", [], "region", -5.1945, -80.6328, "Perú"),
    ("Puno", [], "region", -15.8402, -70.0219, "Perú"),
    ("San Martín", ["san martin"], "region", -6.0342, -76.9717, "Perú · capital: Moyobamba"),
    ("Tacna", [], "region", -18.0066, -70.2463, "Perú"),
    ("Tumbes", [], "region", -3.5669, -80.4515, "Perú"),
    ("Ucayali", [], "region", -8.3791, -74.5539, "Perú · capital: Pucallpa"),
    # --- Ciudades del Perú ---
    ("Lima", ["lima metropolitana", "cercado de lima", "lima cercado", "centro de lima"], "ciudad", -12.0464, -77.0428, "Perú"),
    ("Callao", ["el callao"], "ciudad", -12.0566, -77.1181, "Perú"),
    ("Arequipa", [], "ciudad", -16.3989, -71.5350, "Perú"),
    ("Trujillo", [], "ciudad", -8.1116, -79.0288, "La Libertad, Perú"),
    ("Chiclayo", [], "ciudad", -6.7714, -79.8409, "Lambayeque, Perú"),
    ("Huancayo", [], "ciudad", -12.0651, -75.2049, "Junín, Perú"),
    ("Iquitos", [], "ciudad", -3.7491, -73.2538, "Loreto, Perú"),
    ("Huaraz", [], "ciudad", -9.5278, -77.5278, "Áncash, Perú"),
    ("Chimbote", [], "ciudad", -9.0745, -78.5936, "Áncash, Perú"),
    ("Pucallpa", [], "ciudad", -8.3791, -74.5539, "Ucayali, Perú"),
    ("Juliaca", [], "ciudad", -15.5000, -70.1333, "Puno, Perú"),
    ("Tarapoto", [], "ciudad", -6.4825, -76.3650, "San Martín, Perú"),
    ("Cañete", ["san vicente de cañete", "canete"], "ciudad", -13.0775, -76.3872, "Lima, Perú"),
    ("Chincha", ["chincha alta"], "ciudad", -13.4099, -76.1323, "Ica, Perú"),
    ("Pisco", [], "ciudad", -13.7103, -76.2033, "Ica, Perú"),
    ("Nazca", ["nasca"], "ciudad", -14.8309, -74.9389, "Ica, Perú"),
    ("Paracas", [], "ciudad", -13.8333, -76.2500, "Ica, Perú"),
    ("Huacho", [], "ciudad", -11.1067, -77.6050, "Lima, Perú"),
    ("Huaral", [], "ciudad", -11.4950, -77.2078, "Lima, Perú"),
    ("Mala", [], "ciudad", -12.6581, -76.6311, "Lima, Perú"),
    ("Chilca", [], "ciudad", -12.5214, -76.7372, "Lima, Perú"),
    ("Matucana", [], "ciudad", -11.8447, -76.3786, "Lima, Perú"),
    ("Sullana", [], "ciudad", -4.9039, -80.6853, "Piura, Perú"),
    ("Talara", [], "ciudad", -4.5772, -81.2719, "Piura, Perú"),
    ("Jaén", ["jaen"], "ciudad", -5.7083, -78.8083, "Cajamarca, Perú"),
    ("Ilo", [], "ciudad", -17.6394, -71.3375, "Moquegua, Perú"),
    ("Tingo María", [], "ciudad", -9.2953, -75.9978, "Huánuco, Perú"),
    ("Abancay", [], "ciudad", -13.6339, -72.8814, "Apurímac, Perú"),
    ("Puerto Maldonado", [], "ciudad", -12.5933, -69.1891, "Madre de Dios, Perú"),
    ("Chachapoyas", [], "ciudad", -6.2317, -77.8690, "Amazonas, Perú"),
    ("Moyobamba", [], "ciudad", -6.0342, -76.9717, "San Martín, Perú"),
    ("Machu Picchu", [], "localidad", -13.1631, -72.5450, "Cusco, Perú"),
    # --- Distritos de Lima Metropolitana (centroides aproximados) ---
    ("Ancón", ["ancon"], "distrito", -11.7739, -77.1764, "Lima"),
    ("Ate", ["ate vitarte", "vitarte"], "distrito", -12.0258, -76.9206, "Lima"),
    ("Barranco", [], "distrito", -12.1494, -77.0219, "Lima"),
    ("Breña", ["brena"], "distrito", -12.0597, -77.0503, "Lima"),
    ("Carabayllo", [], "distrito", -11.8569, -77.0383, "Lima"),
    ("Chaclacayo", [], "distrito", -11.9758, -76.7708, "Lima"),
    ("Chorrillos", [], "distrito", -12.1689, -77.0158, "Lima"),
    ("Cieneguilla", [], "distrito", -12.1178, -76.8142, "Lima"),
    ("Comas", [], "distrito", -11.9447, -77.0611, "Lima"),
    ("El Agustino", [], "distrito", -12.0447, -76.9958, "Lima"),
    ("Independencia", [], "distrito", -11.9939, -77.0544, "Lima"),
    ("Jesús María", ["jesus maria"], "distrito", -12.0758, -77.0447, "Lima"),
    ("La Molina", [], "distrito", -12.0806, -76.9367, "Lima"),
    ("La Victoria", [], "distrito", -12.0697, -77.0161, "Lima"),
    ("Lince", [], "distrito", -12.0844, -77.0347, "Lima"),
    ("Los Olivos", [], "distrito", -11.9900, -77.0700, "Lima"),
    ("Lurigancho", ["chosica", "lurigancho-chosica"], "distrito", -11.9372, -76.6972, "Lima"),
    ("Lurín", ["lurin"], "distrito", -12.2753, -76.8708, "Lima"),
    ("Magdalena del Mar", ["magdalena"], "distrito", -12.0911, -77.0697, "Lima"),
    ("Miraflores", [], "distrito", -12.1211, -77.0297, "Lima"),
    ("Pachacámac", ["pachacamac"], "distrito", -12.2297, -76.8597, "Lima"),
    ("Pucusana", [], "distrito", -12.4817, -76.7958, "Lima"),
    ("Pueblo Libre", [], "distrito", -12.0758, -77.0631, "Lima"),
    ("Puente Piedra", [], "distrito", -11.8650, -77.0767, "Lima"),
    ("Punta Hermosa", [], "distrito", -12.3361, -76.8239, "Lima"),
    ("Punta Negra", [], "distrito", -12.3667, -76.7967, "Lima"),
    ("Rímac", ["rimac"], "distrito", -12.0289, -77.0372, "Lima"),
    ("San Bartolo", [], "distrito", -12.3889, -76.7792, "Lima"),
    ("San Borja", [], "distrito", -12.1006, -76.9997, "Lima"),
    ("San Isidro", [], "distrito", -12.0975, -77.0364, "Lima"),
    ("San Juan de Lurigancho", ["sjl"], "distrito", -11.9800, -77.0000, "Lima"),
    ("San Juan de Miraflores", ["sjm"], "distrito", -12.1567, -76.9711, "Lima"),
    ("San Luis", [], "distrito", -12.0761, -76.9939, "Lima"),
    ("San Martín de Porres", ["smp", "san martin de porres"], "distrito", -12.0072, -77.0767, "Lima"),
    ("San Miguel", [], "distrito", -12.0772, -77.0911, "Lima"),
    ("Santa Anita", [], "distrito", -12.0436, -76.9711, "Lima"),
    ("Santa María del Mar", [], "distrito", -12.4058, -76.7731, "Lima"),
    ("Santa Rosa", [], "distrito", -11.8022, -77.1647, "Lima"),
    ("Santiago de Surco", ["surco"], "distrito", -12.1453, -76.9908, "Lima"),
    ("Surquillo", [], "distrito", -12.1128, -77.0208, "Lima"),
    ("Villa El Salvador", ["ves"], "distrito", -12.2131, -76.9367, "Lima"),
    ("Villa María del Triunfo", ["vmt"], "distrito", -12.1608, -76.9417, "Lima"),
    # --- Callao ---
    ("Bellavista", [], "distrito", -12.0619, -77.1047, "Callao"),
    ("Carmen de la Legua", ["carmen de la legua reynoso"], "distrito", -12.0425, -77.0925, "Callao"),
    ("La Perla", [], "distrito", -12.0700, -77.1192, "Callao"),
    ("La Punta", [], "distrito", -12.0722, -77.1625, "Callao"),
    ("Ventanilla", [], "distrito", -11.8753, -77.1269, "Callao"),
    ("Mi Perú", ["mi peru"], "distrito", -11.8544, -77.1250, "Callao"),
]

LEVEL_LABEL = {
    "pais": "país (se representa en su capital)",
    "region": "región (se representa en su capital)",
    "ciudad": "ciudad",
    "localidad": "localidad",
    "distrito": "distrito (centroide aproximado)",
}


def _key(s: str) -> str:
    from ..nlp.text import norm_key
    return norm_key(s)


_INDEX: dict[str, tuple] | None = None


def index() -> dict[str, tuple]:
    global _INDEX
    if _INDEX is None:
        idx = {}
        for entry in PLACES:
            name, aliases = entry[0], entry[1]
            for k in [name] + aliases:
                idx.setdefault(_key(k), entry)
        _INDEX = idx
    return _INDEX


def lookup(name: str):
    return index().get(_key(name))


def find_in_text(query: str):
    """Busca el topónimo conocido más específico contenido en una consulta libre.

    Se priorizan distritos y ciudades sobre regiones y países; ante igual nivel,
    el nombre más largo.
    """
    q = f" {_key(query)} "
    rank = {"distrito": 0, "localidad": 1, "ciudad": 2, "region": 3, "pais": 4}
    found = []
    for k, entry in index().items():
        if f" {k} " in q.replace(",", " ").replace(".", " ").replace("(", " ").replace(")", " "):
            found.append((rank.get(entry[2], 5), -len(k), entry))
    if not found:
        return None
    found.sort(key=lambda t: (t[0], t[1]))
    return found[0][2]
