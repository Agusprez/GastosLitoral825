"""Datos de demostración.

Se usan para probar la app sin configurar Google ni una base real, y para que
quien la reciba pueda ver el producto funcionando en 10 segundos:

    python app.py --demo      (o  streamlit run app.py  con CUENTASCLARAS_DEMO=1)
"""

from __future__ import annotations

from datetime import timedelta

from . import planes as plans
from .dinero import hoy
from .repositorio import Repositorio

CLAVE_DEMO = "CasaFuerte2026"
EMAIL_DEMO = "demo@cuentasclaras.app"
EMAIL_DEMO2 = "bruno@cuentasclaras.app"

GASTOS_DEMO = [
    # (meses atrás, día del mes, concepto, monto, categoría, índice de quién paga)
    (0, 2, "Compra semanal Coto", "48500", "Supermercado", 0),
    (0, 5, "Nafta", "32000", "Auto", 1),
    (0, 8, "Internet Fibertel", "21500", "Internet", 0),
    (0, 11, "Edesur", "18200", "Servicios", 0),
    (0, 14, "Pizza con amigos", "15400", "Salidas", 1),
    (0, 17, "Ferretería", "9800", "Casa", 0),
    (0, 20, "Verdulería", "7300", "Supermercado", 1),
    (0, 23, "Veterinaria", "26000", "Mascotas", 0),
    (1, 3, "Supermercado Dia", "39200", "Supermercado", 1),
    (1, 9, "Gas", "11800", "Servicios", 0),
    (1, 16, "Cine", "12600", "Salidas", 1),
    (1, 22, "Farmacia", "8900", "Salud", 0),
    (2, 4, "Muebles living", "180000", "Casa", 0),
    (2, 18, "Supermercado Jumbo", "55300", "Supermercado", 1),
]


def _fecha_de(meses_atras: int, dia: int):
    """Fecha dentro de un mes anterior, sin pasarse del último día."""
    referencia = hoy().replace(day=1)
    for _ in range(meses_atras):
        referencia = (referencia - timedelta(days=1)).replace(day=1)
    ultimo = ((referencia.replace(day=28) + timedelta(days=4)).replace(day=1)) - timedelta(days=1)
    return referencia.replace(day=min(dia, ultimo.day))


def sembrar(repo: Repositorio, clave: str = CLAVE_DEMO) -> dict:
    """Crea el hogar demo. Si ya existe, devuelve lo que hay."""
    existente = repo.usuario_por_email(EMAIL_DEMO)
    if existente:
        hogares = repo.hogares_de(existente["id"])
        return {
            "creado": False,
            "email": EMAIL_DEMO,
            "clave": clave,
            "hogar": hogares[0] if hogares else None,
        }

    ana = repo.crear_usuario(EMAIL_DEMO, "Ana Demo", clave)
    bruno = repo.crear_usuario(EMAIL_DEMO2, "Bruno Demo", clave)
    hogar = repo.crear_hogar(ana["id"], "Casa Demo")
    repo.unirse_por_codigo(
        bruno["id"], repo.invitar(hogar["id"], ana["id"], rol="admin")["codigo"]
    )
    # Plan Pro para que la demo muestre todo el producto.
    repo.cambiar_plan(hogar["id"], plans.PRO)
    repo.renombrar_hogar(hogar["id"], ana["id"], "Casa Demo")

    personas = [ana["id"], bruno["id"]]
    dia_de_hoy = hoy().day
    for meses_atras, dia, concepto, monto, categoria, quien in GASTOS_DEMO:
        # En el mes en curso no se pueden cargar gastos con fecha futura: los
        # amontonamos en los días que ya transcurrieron.
        dia_efectivo = min(dia, dia_de_hoy) if meses_atras == 0 else dia
        repo.agregar_gasto(
            hogar["id"],
            personas[quien],
            concepto,
            monto,
            categoria,
            personas[quien],
            personas,
            fecha=_fecha_de(meses_atras, dia_efectivo),
        )
    # Un pago parcial para que el saldo no quede en un número redondo.
    repo.registrar_pago(
        hogar["id"],
        bruno["id"],
        bruno["id"],
        ana["id"],
        "40000",
        nota="Transferencia parcial",
    )

    for texto in ("Detergente", "Leche", "Yerba", "Papel higiénico"):
        repo.agregar_compra(hogar["id"], ana["id"], texto)
    primera = repo.compras(hogar["id"], ana["id"])[0]
    repo.cambiar_estado_compra(hogar["id"], bruno["id"], primera["id"], True)

    repo.agregar_compra(hogar["id"], bruno["id"], "Fideos")
    repo.invitar(hogar["id"], ana["id"], rol="miembro", dias=30)

    return {
        "creado": True,
        "email": EMAIL_DEMO,
        "clave": clave,
        "hogar": repo.obtener_hogar(ana["id"], hogar["id"]),
    }


def descripcion_demo(hogar: dict | None = None) -> str:
    return (
        f"Usuario demo: **{EMAIL_DEMO}** · contraseña: **{CLAVE_DEMO}**"
        + (f" · hogar «{hogar.get('nombre')}»" if hogar else "")
    )


def resumen_demo() -> str:  # pragma: no cover - utilidad de consola
    return f"{EMAIL_DEMO} / {CLAVE_DEMO} (hogar «Casa Demo»)"
