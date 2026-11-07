"""Configuración de la aplicación.

La configuración se arma SIEMPRE a partir de un diccionario plano (secretos de
Streamlit o variables de entorno), para que el núcleo no dependa de Streamlit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Mapping

# Prefijo de las variables de entorno. Sirve para despliegues tipo Docker/Render.
PREFIJO = "CUENTASCLARAS_"

# Nombres de variable sin prefijo que también se aceptan (secretos de la v1 y de
# paneles como el de Hugging Face, que no permiten cambiar el nombre).
NOMBRES_DIRECTOS = {
    "sheet_url_gastos",
    "hoja_url",
    "gcp_service_account",
    "gcp_credenciales",
    "gcp_client_email",
    "gcp_private_key",
    "gcp_project_id",
    "imgbb_api_key",
    "clave_cifrado",
    "drive_carpeta_id",
    "url_publica",
    "admins",
}


def _texto(valor: Any, defecto: str = "") -> str:
    if valor is None:
        return defecto
    return str(valor).strip()


def _booleano(valor: Any, defecto: bool = True) -> bool:
    if valor is None or valor == "":
        return defecto
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"1", "si", "sí", "true", "yes", "on", "verdadero"}


def _lista(valor: Any) -> tuple[str, ...]:
    if not valor:
        return ()
    if isinstance(valor, str):
        partes = valor.replace(";", ",").split(",")
        return tuple(p.strip().lower() for p in partes if p.strip())
    return tuple(str(v).strip().lower() for v in valor if str(v).strip())


def _entero(valor: Any, defecto: int) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


@dataclass(frozen=True)
class Config:
    """Parámetros de despliegue. Inmutable: se reemplaza con `replace()`."""

    app_nombre: str = "Cuentas Claras"
    moneda: str = "ARS"
    simbolo: str = "$"

    # Dónde se guardan los datos: "sheets" (Google Sheets, la base de datos
    # elegida: la misma planilla de siempre) o "sqlite" (archivo local, sólo
    # para pruebas sin credenciales de Google).
    almacen: str = "sqlite"
    sqlite_ruta: str = "data/cuentasclaras.db"

    # Google (base de datos y, opcionalmente, comprobantes).
    hoja_url: str = ""
    # Planilla anterior (v1), si los datos viejos quedaron en otro archivo.
    hoja_url_legacy: str = ""
    prefijo_hojas: str = "cc_"
    gcp_credenciales: Mapping[str, Any] | None = None

    # Comprobantes: "imgbb" (servicio externo, como la v1), "drive" (privado en
    # Google Drive) o "local" (disco del servidor).
    medios: str = "local"
    medios_dir: str = "data/comprobantes"
    drive_carpeta_id: str = ""
    imgbb_api_key: str = ""
    max_comprobante_mb: int = 5

    # Cifrado en reposo de todo lo que se guarda (planilla o SQLite).
    cifrado: bool = True
    clave_cifrado: str = ""
    clave_archivo: str = "data/clave.key"

    # Plataforma.
    admins: tuple[str, ...] = ()
    registro_abierto: bool = True
    # Dirección pública de la app: es el link que va en los mensajes de invitación
    # y en los textos de soporte. Viene con la del despliegue actual; se puede
    # sobreescribir con el secreto `url_publica` (útil si cambiás de dominio o si
    # desplegás una copia para otra persona).
    url_publica: str = "https://litoral825.streamlit.app"
    soporte_email: str = "hola@cuentasclaras.app"

    # Comercial.
    precio_mensual: str = "4.900"
    precio_anual: str = "49.000"

    # Datos.
    zona: str = "America/Argentina/Buenos_Aires"
    historial_gratis_meses: int = 12

    @property
    def usa_google(self) -> bool:
        return self.almacen == "sheets" or self.medios == "drive"

    @property
    def precio_mensual_num(self) -> Decimal:
        return Decimal(self.precio_mensual.replace(".", "").replace(",", "."))

    @property
    def precio_anual_num(self) -> Decimal:
        return Decimal(self.precio_anual.replace(".", "").replace(",", "."))

    @property
    def ahorro_anual_pct(self) -> int:
        """Descuento del plan anual respecto de 12 cuotas mensuales."""
        mensual = self.precio_mensual_num * 12
        if mensual <= 0:
            return 0
        return int(round((1 - self.precio_anual_num / mensual) * 100))

    def es_admin(self, email: str) -> bool:
        return (email or "").strip().lower() in self.admins


def desde_entorno(entorno: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Lee variables de entorno con prefijo `CUENTASCLARAS_`.

    Además acepta un puñado de nombres sin prefijo porque así se llaman los
    secretos que ya existían en la versión 1 y porque los hosts tipo Hugging Face
    Spaces inyectan cada secreto con el nombre exacto que se le puso.
    """
    entorno = entorno if entorno is not None else os.environ
    datos: dict[str, Any] = {}
    for clave, valor in entorno.items():
        if clave.upper().startswith(PREFIJO):
            datos[clave[len(PREFIJO):].lower()] = valor
        elif clave.lower() in NOMBRES_DIRECTOS:
            datos[clave.lower()] = valor
    return datos


def _credenciales_desde_partes(combinado: Mapping[str, Any]) -> dict[str, Any] | None:
    """Arma la service account a partir de sus partes.

    Muchos hosts limitan el tamaño de un secreto; el JSON completo de Google ronda
    los 2,4 KB por la `private_key`. Con estas dos variables alcanza.
    """
    correo = _texto(
        combinado.get("gcp_client_email") or combinado.get("client_email")
    )
    clave = str(
        combinado.get("gcp_private_key") or combinado.get("private_key") or ""
    ).strip()
    if not (correo and clave):
        return None
    # En un panel web es común pegar la clave con "\n" literales.
    clave = clave.replace("\\n", "\n")
    if "BEGIN PRIVATE KEY" not in clave:
        return None
    datos = {
        "type": "service_account",
        "client_email": correo,
        "private_key": clave,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    proyecto = _texto(combinado.get("gcp_project_id") or combinado.get("project_id"))
    if proyecto:
        datos["project_id"] = proyecto
    return datos


def _json_o_texto(valor: Any) -> Any:
    """Permite pasar la service account como JSON en una variable de entorno.

    En hosts con contenedores (Render, Fly, Cloud Run) la forma más práctica de
    cargar las credenciales es una variable `CUENTASCLARAS_GCP_CREDENCIALES` con
    el JSON completo en una línea. Si viene el JSON, lo parseamos.
    """
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.startswith("{"):
            try:
                return json.loads(texto)
            except ValueError:
                return None
    return valor


def _ajuste(combinado: Mapping[str, Any], nombre: str) -> Any:
    """Busca un ajuste en el nivel superior y, si no está, dentro de las secciones.

    Es muy común pegar `url_publica = "..."` al final del archivo de secretos: en
    TOML, cualquier clave que venga después de un `[encabezado]` pertenece a esa
    sección, así que termina dentro de `[gcp_service_account]`. En lugar de
    ignorarla en silencio, la encontramos igual.
    """
    if nombre in combinado:
        return combinado[nombre]
    for valor in combinado.values():
        if isinstance(valor, Mapping) and nombre in valor:
            return valor[nombre]
    return None


def armar(datos: Mapping[str, Any] | None = None) -> Config:
    """Combina secretos + entorno + valores por defecto."""
    combinado: dict[str, Any] = {}
    combinado.update(desde_entorno())
    if datos:
        combinado.update({str(k).lower(): v for k, v in datos.items()})

    def ajuste(nombre: str) -> Any:
        return _ajuste(combinado, nombre)

    cfg = Config(
        app_nombre=_texto(ajuste("app_nombre"), Config.app_nombre),
        moneda=_texto(ajuste("moneda"), Config.moneda),
        simbolo=_texto(ajuste("simbolo"), Config.simbolo),
        almacen=_texto(ajuste("almacen"), "").lower() or None,
        medios=_texto(ajuste("medios"), "").lower() or None,
        sqlite_ruta=_texto(ajuste("sqlite_ruta"), Config.sqlite_ruta),
        hoja_url=_texto(ajuste("hoja_url") or ajuste("sheet_url_gastos")),
        hoja_url_legacy=_texto(
            ajuste("hoja_url_legacy")
            or ajuste("sheet_url_legacy")
            or ajuste("hoja_url_v1")
        ),
        prefijo_hojas=_texto(ajuste("prefijo_hojas"), Config.prefijo_hojas).lower(),
        gcp_credenciales=_json_o_texto(
            combinado.get("gcp_credenciales") or combinado.get("gcp_service_account")
        )
        or _credenciales_desde_partes(combinado),
        medios_dir=_texto(ajuste("medios_dir"), Config.medios_dir),
        drive_carpeta_id=_texto(ajuste("drive_carpeta_id")),
        imgbb_api_key=_texto(
            ajuste("imgbb_api_key") or ajuste("imgbb") or ajuste("imgbb_key")
        ),
        max_comprobante_mb=_entero(ajuste("max_comprobante_mb"), Config.max_comprobante_mb),
        cifrado=_booleano(ajuste("cifrado"), True),
        clave_cifrado=_texto(
            ajuste("clave_cifrado") or ajuste("clave") or ajuste("encryption_key")
        ),
        clave_archivo=_texto(ajuste("clave_archivo"), Config.clave_archivo),
        admins=_lista(ajuste("admins")),
        registro_abierto=_booleano(ajuste("registro_abierto"), True),
        url_publica=_texto(ajuste("url_publica") or ajuste("app_url"), Config.url_publica),
        soporte_email=_texto(ajuste("soporte_email"), Config.soporte_email),
        precio_mensual=_texto(ajuste("precio_mensual"), Config.precio_mensual),
        precio_anual=_texto(ajuste("precio_anual"), Config.precio_anual),
        historial_gratis_meses=_entero(
            ajuste("historial_gratis_meses"), Config.historial_gratis_meses
        ),
    )

    # Regla principal: si hay credenciales de Google, la base de datos ES la
    # planilla (es lo que sobrevive a los reinicios de Streamlit Community
    # Cloud y lo que ya venían usando). Sin credenciales, SQLite local para
    # poder probar la app en cualquier máquina.
    almacen = cfg.almacen
    if almacen is None:
        almacen = "sheets" if (cfg.gcp_credenciales and cfg.hoja_url) else "sqlite"
    medios = cfg.medios
    if medios is None:
        # Orden de preferencia: imgbb (si hay clave, es lo que ya venían usando),
        # después Drive (privado) y si no, disco local.
        if cfg.imgbb_api_key:
            medios = "imgbb"
        elif cfg.gcp_credenciales and cfg.drive_carpeta_id:
            medios = "drive"
        else:
            medios = "local"

    return replace(cfg, almacen=almacen, medios=medios)
