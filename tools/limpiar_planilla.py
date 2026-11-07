"""Limpia la planilla de la v1 y simula la importación (sin tocar Google).

    python tools/limpiar_planilla.py --entrada datos_privados/planilla_v1.tsv \
        --salida datos_privados/gastos_litoral825.csv

Qué hace:

* Lee CSV/TSV/XLSX con la misma normalización que usa la app.
* Corrige lo corregible: espacios, «Sin comprobante» → sin comprobante, categorías
  fuera de lista → Otros, conceptos vacíos → «Sin detalle».
* Descarta filas inválidas (fecha ilegible, monto en cero o negativo) y las informa.
* Escribe un CSV listo para subir desde *Hogar → Ajustes → Importar*.
* Simula la importación en memoria (SQLite/RAM) y muestra totales, saldos y la
  transferencia sugerida, para comparar contra la planilla original.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cuentasclaras.modelos import migracion  # noqa: E402
from cuentasclaras.modelos.almacen import MemoryStore  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.dinero import decimal, formatear, parsear_fecha  # noqa: E402
from cuentasclaras.modelos.repositorio import CATEGORIAS, Repositorio  # noqa: E402

ENCABEZADOS = ["Fecha", "Quien", "Concepto", "Monto", "Categoria", "Comprobante"]


def limpiar(filas: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """Normaliza las filas y devuelve (limpias, avisos)."""
    limpias: list[dict[str, str]] = []
    avisos: list[str] = []

    for numero, fila in enumerate(filas, start=2):
        concepto = " ".join((fila.get("concepto") or "").split())
        quien = " ".join((fila.get("quien") or "").split())
        comprobante = (fila.get("comprobante") or "").strip()
        try:
            fecha = parsear_fecha(fila.get("fecha", ""))
        except ValueError:
            avisos.append(f"fila {numero}: fecha ilegible «{fila.get('fecha')}» (se omite)")
            continue

        monto = decimal(fila.get("monto"))
        if monto <= 0:
            avisos.append(
                f"fila {numero}: monto {formatear(monto)} con «{concepto or 'sin detalle'}» "
                f"del {fecha.strftime('%d/%m/%Y')} (se omite)"
            )
            continue

        if not concepto:
            avisos.append(
                f"fila {numero}: sin detalle ({formatear(monto)} de {quien} el "
                f"{fecha.strftime('%d/%m/%Y')}) → queda como «Sin detalle»"
            )
            concepto = "Sin detalle"

        categoria = (fila.get("categoria") or "").strip()
        if categoria not in CATEGORIAS:
            avisos.append(f"fila {numero}: categoría «{categoria}» → Otros")
            categoria = "Otros"

        if comprobante.lower() in {"sin comprobante", "no", "-", ""}:
            comprobante = ""

        limpias.append(
            {
                "Fecha": fecha.strftime("%d/%m/%Y"),
                "Quien": quien,
                "Concepto": concepto,
                "Monto": f"{monto:.2f}",
                "Categoria": categoria,
                "Comprobante": comprobante,
            }
        )
    return limpias, avisos


def escribir(filas: list[dict[str, str]], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=ENCABEZADOS)
        escritor.writeheader()
        escritor.writerows(filas)


def simular(filas: list[dict[str, str]]) -> dict:
    """Importa en memoria y devuelve el resumen que vería la app."""
    config = armar(
        {"almacen": "memoria", "cifrado": False, "sqlite_ruta": str(Path(tempfile.gettempdir()) / "sim.db")}
    )
    repo = Repositorio(MemoryStore(), config)
    nombres = sorted({f["Quien"] for f in filas})
    usuarios = {
        nombre: repo.crear_usuario(
            f"{nombre.lower() or 'x'}@ejemplo.com", nombre or "Sin nombre", "ClaveSegura2026"
        )["id"]
        for nombre in nombres
    }
    hogar = repo.crear_hogar(usuarios[nombres[0]], "Litoral 825")
    for nombre in nombres[1:]:
        repo.unirse_por_codigo(
            usuarios[nombre], repo.invitar(hogar["id"], usuarios[nombres[0]])["codigo"]
        )

    informe = migracion.importar(repo, hogar["id"], filas, usuarios)
    resumen = repo.resumen(hogar["id"], usuarios[nombres[0]], historico=True)
    return {
        "informe": informe,
        "total": resumen["total"],
        "cantidad": resumen["cantidad"],
        "saldos": resumen["saldos"],
        "nombres": resumen["nombres"],
        "transferencias": resumen["transferencias"],
        "por_categoria": resumen["por_categoria"],
        "por_persona": resumen["por_pagado"] if "por_pagado" in resumen else resumen["por_persona"],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    parser = argparse.ArgumentParser(description="Limpia la planilla v1 y simula la importación")
    parser.add_argument("--entrada", required=True)
    parser.add_argument("--salida", required=True)
    parser.add_argument("--no-simular", action="store_true")
    args = parser.parse_args(argv)

    origen = Path(args.entrada)
    filas, compras = migracion.leer_archivo(origen.name, origen.read_bytes())
    print(f"Leídas {len(filas)} filas de gastos y {len(compras)} de compras de {origen.name}")

    limpias, avisos = limpiar(filas)
    destino = Path(args.salida)
    escribir(limpias, destino)

    print(f"\nFilas limpias: {len(limpias)} → {destino}")
    print(f"Total: {formatear(sum((decimal(f['Monto']) for f in limpias), Decimal('0')))}")
    fechas = [parsear_fecha(f["Fecha"]) for f in limpias]
    if fechas:
        print(f"Período: {min(fechas):%d/%m/%Y} a {max(fechas):%d/%m/%Y}")
    print("Por persona:", dict(Counter(f["Quien"] for f in limpias)))
    print("Por categoría:", dict(Counter(f["Categoria"] for f in limpias)))

    if avisos:
        print(f"\nAvisos ({len(avisos)}):")
        for aviso in avisos:
            print(f"  - {aviso}")

    if not args.no_simular and limpias:
        resultado = simular(limpias)
        print("\n--- Simulación de la importación ---")
        print(f"Gastos: {resultado['cantidad']} · Total: {formatear(resultado['total'])}")
        for usuario_id, datos in resultado["saldos"].items():
            print(
                f"  {resultado['nombres'][usuario_id]:<10} "
                f"pagó {formatear(datos['pagado']):>12} · "
                f"le corresponde {formatear(datos['parte']):>12} · "
                f"saldo {formatear(datos['neto']):>12}"
            )
        for transferencia in resultado["transferencias"]:
            print(
                f"  → {transferencia['de_nombre']} le transfiere "
                f"{formatear(transferencia['monto'])} a {transferencia['a_nombre']}"
            )
        print("Categorías:", {k: formatear(v) for k, v in resultado["por_categoria"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
