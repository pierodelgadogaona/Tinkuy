"""Léxicos del español usados por los análisis programáticos.

Son listas cerradas y explícitas: cada recuento que la aplicación muestra puede
rastrearse hasta una de estas entradas. Se priorizan expresiones de uso
periodístico en el español de América Latina y de España.
"""
from __future__ import annotations

STOPWORDS = set("""
a acá ahí al algo algún alguna algunas alguno algunos allá allí ambos ante antes aquel aquella aquellas aquello aquellos
aquí así aun aún aunque bajo bien cada casi cerca como cómo con contra cual cuál cuales cuáles cualquier cuando cuándo
cuanto cuánto cuantos cuántos de del demás dentro desde donde dónde dos durante e el él ella ellas ello ellos en entre
era eran eres es esa esas ese eso esos esta está estaba estaban estado estados estamos están estar estará estas este
esto estos estoy fue fuera fueron fui ha había habían haber habrá han has hasta hay he hemos hubo la las le les lo los
más me mi mí mientras mis misma mismas mismo mismos mucha muchas mucho muchos muy nada ni ningún ninguna ninguno no
nos nosotros nuestra nuestras nuestro nuestros nunca o os otra otras otro otros para pero poco pocos por porque
primero puede pueden pues qué que quien quién quienes se sea sean según ser será serán sería si sí sido siempre
siendo sin sino sobre sois solo sólo son su sus suya suyo tal también tampoco tan tanto te tendrá tenía tener tiene
tienen toda todas todavía todo todos tras tu tú tus u un una unas uno unos usted ustedes va van vez y ya yo
además ayer hoy luego entonces solo cerca mediante via vía hacia tiene tenían podrá podría sus cuyo cuya cuyos cuyas
dijo dice señaló indicó afirmó explicó precisó informó agregó añadió sostuvo manifestó aseguró detalló comentó
este esta estos estas otro otra cada mismo misma sido ser estar haber hacer hecho hace hizo
""".split())

# Conectores y marcadores discursivos por función ------------------------------------------
CONNECTORS: dict[str, list[str]] = {
    "aditivos": ["además", "asimismo", "también", "igualmente", "de igual modo", "de igual manera", "del mismo modo",
                 "por otra parte", "por otro lado", "a su vez", "incluso", "es más", "aparte de", "más aún", "de la misma forma"],
    "adversativos": ["pero", "sin embargo", "no obstante", "aunque", "en cambio", "por el contrario", "pese a",
                     "a pesar de", "aun así", "sino", "mientras que", "con todo", "ahora bien", "de todos modos", "de todas formas"],
    "causales": ["porque", "ya que", "puesto que", "dado que", "debido a", "a causa de", "por culpa de", "gracias a",
                 "como consecuencia de", "a raíz de", "tras", "visto que", "en vista de", "por cuanto", "producto de"],
    "consecutivos": ["por lo tanto", "por tanto", "por ello", "por eso", "así que", "en consecuencia", "por consiguiente",
                     "de modo que", "de manera que", "de ahí que", "con lo que", "lo que generó", "lo que provocó", "por lo que"],
    "temporales": ["luego", "después", "antes", "mientras", "cuando", "posteriormente", "previamente", "entonces",
                   "al mismo tiempo", "hasta que", "desde que", "en tanto", "finalmente", "inicialmente", "más tarde",
                   "minutos después", "horas después", "días después", "poco después", "en un primer momento"],
    "condicionales": ["si", "siempre que", "en caso de", "a menos que", "con tal de que", "salvo que", "a condición de"],
    "finales": ["para que", "a fin de", "con el fin de", "con el objetivo de", "con el propósito de", "de cara a"],
    "reformuladores": ["es decir", "o sea", "esto es", "en otras palabras", "dicho de otro modo", "mejor dicho",
                       "en resumen", "en suma", "en síntesis", "en definitiva", "en conclusión"],
    "ejemplificadores": ["por ejemplo", "como", "tal como", "entre ellos", "entre ellas", "en particular", "concretamente"],
    "ordenadores": ["en primer lugar", "en segundo lugar", "por último", "por una parte", "de un lado", "de otro lado", "primero"],
    "de_atribucion": ["según", "de acuerdo con", "de acuerdo a", "conforme a", "a decir de", "en palabras de",
                      "a juicio de", "en opinión de", "para el especialista", "para la especialista"],
}
# «como», «si», «cuando» y «tras» son muy polisémicos: se cuentan pero se señala su ambigüedad.
AMBIGUOUS_CONNECTORS = {"como", "si", "cuando", "tras", "mientras", "antes", "después", "luego", "entonces", "primero", "sino"}

# Modalidad epistémica ---------------------------------------------------------------------
MODALITY: dict[str, list[str]] = {
    "certeza": ["sin duda", "sin lugar a dudas", "indudablemente", "evidentemente", "claramente", "definitivamente",
                "ciertamente", "efectivamente", "de hecho", "está claro", "es evidente", "es seguro", "con certeza",
                "confirmó", "confirmaron", "se confirmó", "quedó demostrado", "está comprobado", "se comprobó", "es un hecho"],
    "probabilidad": ["probablemente", "es probable", "al parecer", "aparentemente", "presuntamente", "supuestamente",
                     "presunto", "presunta", "presuntos", "presuntas", "se estima", "se calcula", "se presume",
                     "habría", "habrían", "estaría", "estarían", "sería", "serían", "todo indica", "lo más probable"],
    "posibilidad": ["podría", "podrían", "puede que", "pudo", "pudieron", "quizá", "quizás", "tal vez", "posiblemente",
                    "es posible", "cabe la posibilidad", "no se descarta", "no descarta", "no descartan", "eventualmente"],
    "incertidumbre": ["no se sabe", "se desconoce", "se desconocen", "aún no se ha determinado", "aún no se ha precisado",
                      "no está claro", "por determinar", "no se precisó", "sin precisar", "no se ha determinado",
                      "se investiga", "se investigan", "materia de investigación", "no se conoce", "no han sido difundidos",
                      "no fue precisado", "se encuentra en evaluación", "aún se desconoce", "es incierto"],
    "hipotesis": ["hipótesis", "líneas de investigación", "línea de investigación", "se baraja", "se barajan",
                  "en caso de", "de confirmarse", "de comprobarse", "teoría", "versión preliminar", "preliminar", "preliminares"],
    "atribucion": ["según", "de acuerdo con", "de acuerdo a", "conforme a", "a decir de", "en palabras de", "citado por",
                   "consultado por", "consultada por", "fuentes de", "fuentes cercanas", "trascendió", "se informó"],
}

# Verbos de declaración (infinitivos): se conjugan programáticamente --------------------------------
DECLARATIVE_INFINITIVES = [
    "afirmar", "señalar", "indicar", "informar", "explicar", "precisar", "agregar", "añadir", "manifestar", "declarar",
    "asegurar", "detallar", "comentar", "relatar", "contar", "narrar", "denunciar", "acusar", "advertir", "alertar",
    "aclarar", "anunciar", "confirmar", "negar", "admitir", "reconocer", "responder", "sostener", "decir", "expresar",
    "destacar", "subrayar", "enfatizar", "insistir", "recordar", "revelar", "apuntar", "referir", "sugerir", "pedir",
    "exigir", "reclamar", "cuestionar", "criticar", "lamentar", "reiterar", "puntualizar", "argumentar", "alegar",
    "opinar", "considerar", "estimar", "calificar", "comunicar", "reportar", "notificar", "replicar", "admitir",
    "concluir", "plantear", "proponer", "solicitar", "rechazar", "desmentir", "atribuir", "atestiguar", "testificar",
]
IRREGULAR_DECLARATIVE_FORMS = {
    "decir": ["dijo", "dijeron", "dice", "dicen", "decía", "decían", "ha dicho", "han dicho", "dirá", "dirán", "diría", "dicho"],
    "sostener": ["sostuvo", "sostuvieron", "sostiene", "sostienen", "sostenía", "sostenido"],
    "reconocer": ["reconoció", "reconocieron", "reconoce", "reconocen", "reconocido"],
    "advertir": ["advirtió", "advirtieron", "advierte", "advierten", "advertido"],
    "negar": ["negó", "negaron", "niega", "niegan", "negado"],
    "referir": ["refirió", "refirieron", "refiere", "refieren", "referido"],
    "sugerir": ["sugirió", "sugirieron", "sugiere", "sugieren"],
    "pedir": ["pidió", "pidieron", "pide", "piden", "pedido"],
    "contar": ["contó", "contaron", "relató"],
    "atribuir": ["atribuyó", "atribuyeron", "atribuye", "atribuyen"],
    "concluir": ["concluyó", "concluyeron", "concluye", "concluyen"],
    "recordar": ["recordó", "recordaron", "recuerda", "recuerdan"],
    "insistir": ["insistió", "insistieron", "insiste", "insisten"],
    "exigir": ["exigió", "exigieron", "exige", "exigen"],
}
# Formas de presente ambiguas con sustantivos o adjetivos: no se cuentan.
AMBIGUOUS_DECLARATIVE = {"cuenta", "cuentan", "denuncia", "denuncias", "precisa", "precisas", "crítica", "critica",
                         "reclamo", "plantea", "pide", "opina", "estima", "considera", "considerado", "estimado", "calificado",
                         "comunicado", "reporte", "relato", "señala", "atribuida"}

INTENSIFIERS = ["muy", "sumamente", "extremadamente", "totalmente", "absolutamente", "completamente", "enormemente",
                "altamente", "tremendamente", "terriblemente", "increíblemente", "realmente", "verdaderamente",
                "demasiado", "excesivamente", "profundamente", "gravemente", "seriamente", "brutalmente", "sobremanera",
                "en extremo", "de lejos", "a todas luces", "nada menos que", "ni más ni menos"]
ATTENUATORS = ["algo", "un poco", "relativamente", "ligeramente", "apenas", "más o menos", "en cierta medida",
               "en cierto modo", "parcialmente", "levemente", "moderadamente", "aparentemente", "medianamente",
               "prácticamente", "casi", "alrededor de", "cerca de", "aproximadamente", "unos", "unas"]

EMOTION_WORDS = [
    "dolor", "llanto", "lágrimas", "lágrima", "angustia", "desesperación", "miedo", "terror", "pánico", "pavor",
    "tristeza", "pena", "consternación", "conmoción", "indignación", "rabia", "furia", "ira", "impotencia", "luto",
    "duelo", "sufrimiento", "tragedia", "trágico", "trágica", "drama", "dramático", "dramática", "horror", "horrible",
    "desgarrador", "desgarradora", "conmovedor", "conmovedora", "esperanza", "alivio", "alegría", "felicidad",
    "agradecimiento", "gratitud", "solidaridad", "voz quebrada", "entre lágrimas", "gritos", "gritaban", "lloraban",
    "clamor", "desconsuelo", "desconsolado", "desconsolada", "estremecedor", "estremecedora", "aterrador", "aterradora",
    "temor", "zozobra", "incertidumbre", "preocupación", "alarma",
]
SENSATIONAL_WORDS = [
    "tragedia", "horror", "terror", "pánico", "caos", "infierno", "masacre", "carnicería", "dantesco", "dantesca",
    "escalofriante", "estremecedor", "estremecedora", "impactante", "impactantes", "brutal", "brutales", "salvaje",
    "macabro", "macabra", "espeluznante", "aterrador", "aterradora", "insólito", "insólita", "increíble", "increíbles",
    "conmoción", "shock", "viral", "bomba de tiempo", "pesadilla", "violento", "violenta", "fatal", "fatídico",
    "fatídica", "sangriento", "sangrienta", "desgarrador", "desgarradora", "cobrando vidas", "sigue cobrando",
    "nadie quiso", "una vez más", "otra vez", "de nuevo", "mortal", "mortales", "dramático", "dramática",
]

INSTITUTIONAL_FORMULAS = [
    "de conformidad con", "en el marco de", "a fin de", "dispuso", "se dispuso", "resolución", "decreto supremo",
    "decreto de urgencia", "en cumplimiento de", "se procedió", "procedió a", "el referido", "la referida", "el citado",
    "la citada", "dicho", "dicha", "diligencias de ley", "conforme a ley", "las acciones correspondientes",
    "las medidas correspondientes", "en coordinación con", "comunicado oficial", "mediante un comunicado",
    "de acuerdo con el protocolo", "según el protocolo", "personal de", "las autoridades competentes", "se informa",
    "la entidad", "el sector", "la institución", "la dependencia", "fiscalización", "supervisión",
]
LEGAL_TERMS = [
    "fiscalía", "fiscal", "juez", "jueza", "juzgado", "poder judicial", "tribunal", "sala", "imputado", "imputada",
    "investigado", "investigada", "detenido", "detenida", "detención", "prisión preventiva", "denuncia", "denunció",
    "delito", "delitos", "presunto", "presunta", "homicidio", "homicidio culposo", "lesiones", "lesiones graves",
    "sentencia", "condena", "acusación", "acusación constitucional", "medida cautelar", "comparecencia", "querella",
    "investigación preliminar", "investigaciones preliminares", "investigación preparatoria", "diligencias",
    "dosaje etílico", "peritaje", "pericial", "peritos", "flagrancia", "procuraduría", "defensa legal", "abogado",
    "abogada", "situación legal", "situación jurídica", "responsabilidad penal", "responsabilidad civil", "infracción",
    "infracciones", "papeletas", "sanción", "sanciones", "multa", "multas", "autorización", "licencia",
]
AGENCIES = {
    "EFE": "Agencia EFE", "AFP": "Agence France-Presse", "Reuters": "Reuters", "AP": "Associated Press",
    "Associated Press": "Associated Press", "Europa Press": "Europa Press", "Andina": "Agencia Andina",
    "ANSA": "ANSA", "DPA": "DPA", "Bloomberg": "Bloomberg", "Xinhua": "Xinhua", "Sputnik": "Sputnik",
    "Notimex": "Notimex", "Prensa Latina": "Prensa Latina", "Telam": "Télam", "Télam": "Télam",
}
COMMUNIQUE_MARKERS = ["comunicado", "nota de prensa", "pronunciamiento", "conferencia de prensa", "informe", "reporte",
                      "oficio", "resolución", "documento", "boletín", "parte policial", "atestado", "acta",
                      "redes sociales", "cuenta oficial", "publicación en", "tuit", "trino", "mensaje en x",
                      "mensaje en twitter", "en facebook", "en instagram", "en tiktok"]
COLLOQUIAL = ["chofer", "carro", "plata", "chamba", "pata", "causa", "bronca", "jale", "ni modo", "a full", "harto",
              "harta", "papeleta", "combi", "cúster", "broder", "chévere", "bacán", "jato", "huevear", "cholo",
              "de frente", "al toque", "toque", "metió", "le cayó", "se armó"]

# Palabras de clase cerrada para el etiquetado heurístico -------------------------------------------
DETERMINERS = set("el la los las un una unos unas este esta estos estas ese esa esos esas aquel aquella aquellos aquellas "
                  "mi mis tu tus su sus nuestro nuestra nuestros nuestras vuestro vuestra al del cada todo toda todos todas "
                  "otro otra otros otras varios varias algunos algunas ningún ninguna cierto cierta tanto tanta tantos tantas "
                  "dicho dicha dichos dichas cuyo cuya".split())
PREPOSITIONS = set("a ante bajo cabe con contra de desde durante en entre hacia hasta mediante para por según sin so sobre tras "
                   "versus vía".split())
CONJUNCTIONS = set("y e ni o u pero sino aunque que porque pues si como cuando mientras donde".split())
PRONOUNS = set("yo tú él ella ello nosotros nosotras vosotros vosotras ellos ellas usted ustedes me te se nos os lo la le "
               "los las les mí ti sí conmigo contigo consigo esto eso aquello quien quienes cual cuales alguien nadie algo "
               "nada".split())
AUXILIARIES = set("ha han he hemos había habían hubo habrá habrán habría habrían es son era eran fue fueron será serán sería "
                  "serían está están estaba estaban estuvo estuvieron estará estarán sea sean siendo sido estado haya hayan "
                  "hay".split())
IRREGULAR_PARTICIPLES = set("muerto muerta muertos muertas puesto puesta puestos puestas hecho hecha hechos hechas dicho dicha "
                            "dichos dichas visto vista vistos vistas escrito escrita escritos escritas abierto abierta abiertos "
                            "abiertas cubierto cubierta cubiertos cubiertas roto rota rotos rotas vuelto vuelta resuelto resuelta "
                            "impreso impresa provisto provista devuelto devuelta descubierto descubierta preso presa "
                            "electo electa frito frita".split())
NON_PARTICIPLE_ADO = set("estado lado cuidado pasado mercado grado soldado abogado abogada senado delegado delegada "
                         "diputado diputada aliado aliada privado privada dado nado prado helado bocado legado juzgado "
                         "partido sentido ruido vestido marido apellido sonido contenido nido olvido gemido latido "
                         "comunicado resultado mandado candidato candidata ciudad todo toda nada cada medida vida salida "
                         "llegada partida jornada mirada entrada temporada madrugada comida bebida herida heridas caída "
                         "avenida unidad unidades seguido".split())
# Sustantivos frecuentes terminados en -ría/-rías que no son condicionales
NON_CONDITIONAL_RIA = set("secretaría comisaría notaría fiscalía mayoría minoría categoría alegría galería batería librería "
                          "ingeniería ganadería cafetería tesorería lotería porquería consejería auditoría asesoría "
                          "procuraduría defensoría contraloría superintendencia veterinaría guardería panadería jefatura "
                          "artillería caballería infantería mercadería joyería lavandería peluquería ferretería "
                          "señoría policía economía energía compañía garantía".split())
CONDITIONAL_ERIA = set("debería deberían sería serían creería leería tendería comería haría harían".split())

NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciséis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiún": 21, "veintiuno": 21,
    "veintidós": 22, "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "trescientos": 300, "quinientos": 500, "mil": 1000, "millón": 1_000_000,
    "decenas": None, "cientos": None, "centenares": None, "miles": None, "docena": 12, "media docena": 6,
}
UNIT_PATTERNS = [
    (r"%|por ciento|porciento", "porcentaje", "%"),
    (r"soles|s/\.?|nuevos soles", "moneda", "S/"),
    (r"d[oó]lares|us\$|\$", "moneda", "USD"),
    (r"euros|€", "moneda", "EUR"),
    (r"pesos", "moneda", "pesos"),
    (r"kil[oó]metros? por hora|km/h", "medida", "km/h"),
    (r"kil[oó]metros?|km", "medida", "km"),
    (r"metros?|m\b", "medida", "m"),
    (r"toneladas?|t\b", "medida", "t"),
    (r"hect[aá]reas?|ha\b", "medida", "ha"),
    (r"litros?", "medida", "l"),
    (r"kilos?|kilogramos?|kg", "medida", "kg"),
    (r"grados?", "medida", "°"),
    (r"horas?", "duracion", "horas"),
    (r"minutos?", "duracion", "minutos"),
    (r"d[ií]as", "duracion", "días"),
    (r"semanas?", "duracion", "semanas"),
    (r"meses", "duracion", "meses"),
    (r"años", "duracion_o_edad", "años"),
]

TITLES_BEFORE_PERSON = set("señor señora sr sra don doña doctor doctora dr dra ingeniero ingeniera ing licenciado licenciada "
                           "lic ministro ministra viceministro viceministra presidente presidenta alcalde alcaldesa "
                           "gobernador gobernadora congresista senador senadora diputado diputada fiscal juez jueza "
                           "comandante coronel general capitán teniente sargento suboficial mayor jefe jefa director "
                           "directora gerente vocero vocera especialista experto experta padre madre hermano hermana "
                           "hijo hija esposo esposa conductor pasajero pasajera".split())
ORG_KEYWORDS = ["ministerio", "policía", "fiscalía", "municipalidad", "gobierno", "congreso", "poder judicial",
                "hospital", "clínica", "empresa", "transportes", "superintendencia", "universidad", "defensoría",
                "contraloría", "cuerpo general", "compañía", "asociación", "sindicato", "federación", "banco",
                "fundación", "instituto", "consejo", "comisión", "dirección", "división", "unidad", "oficina",
                "colegio", "corte", "tribunal", "juzgado", "procuraduría", "agencia", "organización", "partido",
                "frente", "alianza", "coordinadora", "colectivo", "servicio", "samu", "sutran", "pnp", "mtc", "minsa",
                "essalud", "sunat", "indecopi", "onu", "oms", "ops", "unicef", "s.a.", "sac", "s.a.c.", "eirl"]
PLACE_KEYWORDS = ["avenida", "av.", "jirón", "jr.", "calle", "plaza", "parque", "puente", "carretera", "panamericana",
                  "kilómetro", "km", "distrito", "provincia", "región", "departamento", "ciudad", "pueblo", "caserío",
                  "comunidad", "barrio", "urbanización", "asentamiento", "playa", "río", "lago", "cerro", "nevado",
                  "volcán", "valle", "bahía", "puerto", "aeropuerto", "terminal", "estación", "frontera", "vía expresa",
                  "carretera central", "morgue", "comisaría", "penal", "mercado", "estadio"]

GIVEN_NAMES = set("""
ana andrea antonio carlos carmen césar cristina daniel david diana diego eduardo elena elizabeth ernesto fernando
francisco gabriel gabriela gloria gustavo héctor hugo isabel jaime javier jesús jorge josé josefina juan juana julia
julio karina laura lucía luis luisa manuel marco marcos margarita maría mariana mario marta martín mateo miguel mónica
nancy nelly nicolás norma óscar pablo patricia paula pedro rafael ramón raúl ricardo roberto rocío rosa rosario
santiago sergio silvia sofía susana teresa valeria verónica víctor walter yolanda alberto alejandro alicia ángel
beatriz camila clara claudia dina dora edgar elsa enrique esther fabiola felipe flor gerardo gonzalo guillermo
irene iván jimena joaquín jonathan julián keiko liliana lourdes lorena luciano marcela mercedes milagros natalia
nelson olga omar pilar renzo rubén samuel sandra teodoro tomás vanessa vicente ximena zoila mariela fiorella
""".split())
