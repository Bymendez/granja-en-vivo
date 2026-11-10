"""
Granja sostenible - Pagina en tiempo real
Recibe los datos de los dos ESP32 (bovino y avicola) y los muestra en la pagina.
No usa base de datos: guarda en memoria el ultimo estado y los ultimos eventos.

Rutas:
  POST /api/bovino    -> lo llama el ESP32 del comedero bovino
  POST /api/avicola   -> lo llama el ESP32 del galpon
  GET  /api/estado    -> lo consulta la pagina cada 2 segundos
  GET  /              -> la pagina web
"""
import os
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

CLAVE_API = os.environ.get("CLAVE_API", "granja701n")
SEGUNDOS_EN_LINEA = 12      # si un ESP32 no envia nada en este tiempo, sale "sin senal"
MAX_EVENTOS = 40            # eventos que se guardan por modulo
MODULOS = ("bovino", "avicola")

app = Flask(__name__, static_folder=None)
CARPETA = Path(__file__).parent / "static"

candado = threading.Lock()
memoria = {m: {"estado": None, "ultimo_contacto": None, "eventos": deque(maxlen=MAX_EVENTOS)} for m in MODULOS}
contador = {"eventos": 0}


@app.post("/api/<modulo>")
def recibir(modulo):
    if modulo not in MODULOS:
        return jsonify(error="Modulo desconocido"), 404
    if request.headers.get("X-Clave", "") != CLAVE_API:
        return jsonify(error="Clave incorrecta"), 401
    dato = request.get_json(silent=True)
    if not isinstance(dato, dict) or "tipo" not in dato:
        return jsonify(error="JSON invalido o sin campo tipo"), 400

    ahora = time.time()
    with candado:
        m = memoria[modulo]
        m["ultimo_contacto"] = ahora
        dato["recibido"] = ahora
        if dato["tipo"] == "estado":
            m["estado"] = dato
        else:
            contador["eventos"] += 1
            dato["id"] = contador["eventos"]
            dato["modulo"] = modulo
            m["eventos"].appendleft(dato)
    return jsonify(ok=True)


@app.get("/api/estado")
def estado():
    ahora = time.time()
    salida = {"servidor": ahora}
    with candado:
        for nombre, m in memoria.items():
            ult = m["ultimo_contacto"]
            salida[nombre] = {
                "en_linea": ult is not None and ahora - ult < SEGUNDOS_EN_LINEA,
                "hace_s": None if ult is None else round(ahora - ult, 1),
                "estado": m["estado"],
                "eventos": list(m["eventos"]),
            }
    respuesta = jsonify(salida)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.get("/salud")
def salud():
    return jsonify(ok=True)


@app.get("/")
def inicio():
    respuesta = send_from_directory(CARPETA, "index.html")
    respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@app.get("/img/<path:archivo>")
def imagenes(archivo):
    respuesta = send_from_directory(CARPETA / "img", archivo)
    respuesta.headers["Cache-Control"] = "public, max-age=86400"
    return respuesta


if __name__ == "__main__":
    # Para probar en el computador: python main.py  ->  http://localhost:8000
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True)
