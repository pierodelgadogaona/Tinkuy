"""Registro de las diez fases metodológicas (cada una es un módulo independiente)."""
from . import (f01_identificacion, f02_estructura, f03_cronologia, f04_geografia, f05_semantica, f06_datos, f07_lenguaje,
               f08_actores, f09_fuentes, f10_multimedia)

REGISTRY = {m.PHASE.number: m.PHASE for m in (f01_identificacion, f02_estructura, f03_cronologia, f04_geografia, f05_semantica,
                                               f06_datos, f07_lenguaje, f08_actores, f09_fuentes, f10_multimedia)}
