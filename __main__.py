"""Arranque: python -m tinkuy"""
import uvicorn

from .config import settings

if __name__ == "__main__":
    print(f"Tinkuy en http://{settings.host}:{settings.port}  ·  modelo: {settings.llm_status()['proveedor']} "
          f"({'configurado' if settings.llm_status()['configurado'] else 'no configurado'})")
    uvicorn.run("tinkuy.app:app", host=settings.host, port=settings.port, log_level="warning")
