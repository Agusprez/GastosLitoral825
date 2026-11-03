"""Importa los datos de la versión 1 a Cuentas Claras v2.

Orígenes soportados:

* `--origen sheets` (por defecto): lee las pestañas `Gastos` y `Lista_Compras` de
  la misma planilla que ya usaban. **No modifica ni borra nada**: la v2 escribe en
  pestañas nuevas con prefijo `cc_`.
* `--origen csv`: lee un CSV exportado (columnas fecha, quien, concepto, monto,
  categoria, comprobante).

Ejemplos
--------
    # Ver qué haría, sin escribir nada
    python tools/importar_planilla.py --usuarios "Agustin=agus@x.com,Jorge=jorge@x.com" \
        --hogar "Casa San Pedro"

    # Importar de verdad
    python tools/importar_planilla.py --usuarios "Agustin=agus@x.com,Jorge=jorge@x.com" \
        --hogar "Casa San Pedro" --aplicar

    # Desde un CSV, contra una base local
    python tools/importar_planilla.py --origen csv --csv gastos.csv --aplicar

Las claves salen de `--claves "Agustin=Clave1,Jorge=Clave2"` o de la sección
`passwords` de los secretos de la v1. Si un usuario ya existe (por email) se usa
ese y no se toca su contraseña.
"""

from __future__ import annotations

import argparse
import csv
import secrets
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cuentasclaras.modelos import planes  # noqa: E402
from cuentasclaras.modelos.almacen import ErrorAlmacen  # noqa: E402
from cuentasclaras.modelos.configuracion import armar  # noqa: E402
from cuentasclaras.modelos.dinero import parsear_fecha  # noqa: E402
from cuentasclaras.modelos.fabrica import abrir_almacen  # noqa: E402
from cuentasclaras.modelos.repositorio import CATEGORIAS, ErrorNegocio, Repositorio  # noqa: E402

ALIAS = {
    "fecha": ("fecha", "date", "dia", "día"),
    "quien": ("quien", "quién", "pagado_por", "quien pago", "quién pagó", "who", "usuario"),
    "concepto": ("concepto", "detalle", "descripcion", "descripción", "concept"),
    "monto": ("monto", "importe", "valor", "total", "amount"),
    "categoria": ("categoria", "categoría", "category", "rubro"),
    "comprobante": ("comprobante", "ticket", "foto", "imagen", "receipt"),
}

CLAVE_PROVISORIA = "CambiarEstaClave2026"


@dataclass
class Informe:
    importados: int = 0
    omitidos: int = 0
    compras: int = 0
    errores: list[str] = field(default_factory=list)
    usuarios_creados: list[tuple[str, str, str]] = field(default_factory=list)

    def resumen(self) -> str:
        lineas = [
            f"Gastos importados : {self.importados}",
            f"Gastos omitidos   : {self.omitidos}",
            f"Compras anotadas  : {self.compras}",
        ]
        if self.usuarios_creados:
            lineas.append("\nCuentas creadas (cambiá la contraseña al entrar):")
            for nombre, email, clave in self.usuarios_creados:
                lineas.append(f"  {nombre} <{email}> · contraseña: {clave}")
        if self.errores:
            lineas.append(f"\nAvisos ({len(self.errores)}):")
            lineas.extend(f"  - {e}" for e in self.errores[:30])
            if len(self.errores) > 30:
                lineas.append(f"  … y {len(self.errores) - 30} más")
        return "\n".join(lineas)


# --------------------------------------------------------------------------- #
# Lectura de datos
# --------------------------------------------------------------------------- #
def normalizar_fila(fila: dict[str, Any]) -> dict[str, str]:
    claves = {str(k).strip().lower(): (v if v is not None else "") for k, v in fila.items()}
    salida: dict[str, str] = {}
    for campo, alias in ALIAS.items():
        for nombre in alias:
            if nombre in claves and str(claves[nombre]).strip() != "":
                salida[campo] = str(claves[nombre]).strip()
                break
    return salida


def leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        return [normalizar_fila(fila) for fila in lector]


def leer_planilla(url: str, credenciales: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Lee las pestañas de la v1 sin tocarlas."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Faltan gspread/google-auth: pip install -r requirements.txt") from exc

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(dict(credenciales), scopes=scopes)
    libro = gspread.authorize(creds).open_by_url(url)
    return _filas(libro, "Gastos"), _filas(libro, "Lista_Compras")


def _filas(libro, titulo: str) -> list[dict[str, str]]:
    try:
        hoja = libro.worksheet(titulo)
    except Exception:  # noqa: BLE001 - la pestaña puede no existir
        return []
    valores = hoja.get_all_values()
    if len(valores) < 2:
        return []
    encabezados = [c.strip() for c in valores[0]]
    salida = []
    for cruda in valores[1:]:
        if not any(str(c).strip() for c in cruda):
            continue
        fila = {encabezados[i]: cruda[i] for i in range(min(len(encabezados), len(cruda)))}
        if any(str(v).strip() for v in fila.values()):
            salida.append(normalizar_fila(fila))
    return salida


# --------------------------------------------------------------------------- #
# Usuarios y hogar
# --------------------------------------------------------------------------- #
def parsear_pares(texto: str) -> dict[str, str]:
    """`"Agustin=agus@x.com,Jorge=jorge@x.com"` -> dict."""
    salida: dict[str, str] = {}
    for trozo in (texto or "").split(","):
        if "=" not in trozo:
            continue
        nombre, valor = trozo.split("=", 1)
        if nombre.strip() and valor.strip():
            salida[nombre.strip()] = valor.strip()
    return salida


def asegurar_usuarios(
    repo: Repositorio, personas: dict[str, str], claves: dict[str, str], aplicar: bool
) -> tuple[dict[str, str], Informe]:
    """Devuelve {nombre: usuario_id} creando las cuentas que falten."""
    informe = Informe()
    ids: dict[str, str] = {}
    if not personas:
        raise SystemExit(
            "Indicá las personas con --usuarios \"Nombre=email,Nombre2=email2\"."
        )
    for nombre, email in personas.items():
        existente = repo.usuario_por_email(email)
        if existente:
            ids[nombre] = existente["id"]
            continue
        clave = claves.get(nombre) or f"{secrets.token_urlsafe(6)}Aa1"
        if not aplicar:
            informe.usuarios_creados.append((nombre, email, clave))
            ids[nombre] = f"pendiente:{nombre}"
            continue
        try:
            usuario = repo.crear_usuario(email, nombre, clave)
        except ErrorNegocio as exc:
            raise SystemExit(f"No se pudo crear el usuario {nombre} ({email}): {exc}") from exc
        ids[nombre] = usuario["id"]
        informe.usuarios_creados.append((nombre, email, clave))
    return ids, informe


def asegurar_hogar(repo: Repositorio, nombre: str, propietario_id: str, aplicar: bool) -> str:
    for hogar in repo.hogares_de(propietario_id):
        if hogar["nombre"].strip().lower() == nombre.strip().lower():
            return hogar["id"]
    if not aplicar:
        return "pendiente:hogar"
    hogar = repo.crear_hogar(propietario_id, nombre)
    return hogar["id"]


def sumar_miembros(repo: Repositorio, hogar_id: str, ids: dict[str, str], aplicar: bool) -> None:
    if not aplicar:
        return
    propietario = next(iter(ids.values()))
    for usuario_id in ids.values():
        if usuario_id == propietario or not usuario_id:
            continue
        if repo.rol_en(hogar_id, usuario_id):
            continue
        invitacion = repo.invitar(hogar_id, propietario, rol="miembro", usos_max=1)
        repo.unirse_por_codigo(usuario_id, invitacion["codigo"])


# --------------------------------------------------------------------------- #
# Importación
# --------------------------------------------------------------------------- #
def importar(
    repo: Repositorio,
    hogar_id: str,
    filas: list[dict[str, str]],
    ids: dict[str, str],
    aplicar: bool = True,
    compras: list[dict[str, str]] | None = None,
) -> Informe:
    informe = Informe()
    participantes = [uid for uid in ids.values() if uid]

    def _resolver(nombre: str) -> str:
        buscado = (nombre or "").strip().lower()
        for clave, usuario_id in ids.items():
            if clave.lower() == buscado:
                return usuario_id
        return ""

    for numero, fila in enumerate(filas, start=2):
        concepto = (fila.get("concepto") or "").strip()
        monto = fila.get("monto") or ""
        try:
            fecha = parsear_fecha(fila.get("fecha", ""))
        except ValueError:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: fecha inválida {fila.get('fecha')!r}")
            continue
        if not concepto:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: sin detalle")
            continue
        quien = _resolver(fila.get("quien", ""))
        if not quien:
            informe.omitidos += 1
            informe.errores.append(
                f"fila {numero}: «{fila.get('quien')}» no está en --usuarios"
            )
            continue
        categoria = fila.get("categoria") or "Otros"
        if categoria not in CATEGORIAS:
            categoria = "Otros"
        if not aplicar:
            informe.importados += 1
            continue
        try:
            repo.agregar_gasto(
                hogar_id,
                quien,
                concepto,
                monto,
                categoria,
                quien,
                participantes,
                fecha=fecha,
                comprobante=fila.get("comprobante", ""),
            )
            informe.importados += 1
        except ErrorNegocio as exc:
            informe.omitidos += 1
            informe.errores.append(f"fila {numero}: {exc}")

    for indice, compra in enumerate(compras or [], start=2):
        texto = (compra.get("concepto") or compra.get("texto") or "").strip()
        if not texto:
            informe.omitidos += 1
            continue
        if aplicar and ids:
            try:
                repo.agregar_compra(hogar_id, next(iter(ids.values())), texto)
                informe.compras += 1
            except ErrorNegocio as exc:
                informe.errores.append(f"compra {indice}: {exc}")
    return informe


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def leer_secretos(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    with ruta.open("rb") as archivo:
        return tomllib.load(archivo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importar datos de la v1 a Cuentas Claras v2")
    parser.add_argument("--origen", choices=["sheets", "csv"], default="sheets")
    parser.add_argument("--csv", help="CSV con los gastos (con --origen csv)")
    parser.add_argument("--compras-csv", help="CSV con la lista de compras (opcional)")
    parser.add_argument("--usuarios", required=True, help='"Nombre=email,Nombre2=email2"')
    parser.add_argument("--claves", default="", help='"Nombre=clave,..." (opcional)')
    parser.add_argument("--hogar", default="Casa San Pedro")
    parser.add_argument("--secrets", default=str(RAIZ / ".streamlit" / "secrets.toml"))
    parser.add_argument("--aplicar", action="store_true", help="Escribe los datos")
    parser.add_argument(
        "--plan",
        choices=["gratis", "pro"],
        default="gratis",
        help="Plan con el que queda el hogar importado",
    )
    args = parser.parse_args(argv)

    secretos = leer_secretos(Path(args.secrets))
    config = armar(secretos)
    try:
        store, origen_clave = abrir_almacen(config)
    except ErrorAlmacen as exc:
        print(f"No se pudo abrir el almacenamiento: {exc}")
        return 1

    print(f"Almacén: {store.ping()}")
    print(f"Cifrado: {origen_clave or 'SIN CLAVE (los datos se guardan en claro)'}")
    if not origen_clave and config.almacen == "sheets":
        print(
            "  Aviso: generá una clave con tools/generar_clave.py y agregala como "
            "clave_cifrado antes de importar datos reales."
        )

    repo = Repositorio(store, config)

    if args.origen == "csv":
        if not args.csv:
            print("Falta --csv")
            return 1
        filas = leer_csv(Path(args.csv))
        compras = leer_csv(Path(args.compras_csv)) if args.compras_csv else []
    else:
        if not (config.gcp_credenciales and config.hoja_url):
            print("Faltan gcp_service_account / sheet_url_gastos en los secretos.")
            return 1
        filas, compras = leer_planilla(config.hoja_url, dict(config.gcp_credenciales))

    print(f"Filas de gastos leídas: {len(filas)} · compras: {len(compras)}")

    personas = parsear_pares(args.usuarios)
    claves = parsear_pares(args.claves)
    if not claves:
        passwords = secretos.get("passwords") or {}
        claves = {str(k): str(v) for k, v in passwords.items()}

    ids, informe = asegurar_usuarios(repo, personas, claves, args.aplicar)
    propietario = next(iter(ids.values()))
    hogar_id = asegurar_hogar(repo, args.hogar, propietario, args.aplicar)

    if args.aplicar:
        # Plan Pro durante la importación para no chocar con el límite mensual.
        repo.cambiar_plan(hogar_id, planes.PRO)
        sumar_miembros(repo, hogar_id, ids, args.aplicar)

    resultado = importar(repo, hogar_id, filas, ids, args.aplicar, compras)
    informe.importados = resultado.importados
    informe.omitidos += resultado.omitidos
    informe.compras = resultado.compras
    informe.errores.extend(resultado.errores)

    if args.aplicar:
        repo.cambiar_plan(hogar_id, args.plan)

    print()
    print(informe.resumen())
    if not args.aplicar:
        print("\n(Modo informe: no se escribió nada. Volvé a correr con --aplicar.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
