"""Vista compartida: arranque de sesión, estilos y componentes reutilizables.

La vista no decide reglas de negocio: arma el contexto (modelo + controladores)
y dibuja. Toda acción pasa por un controlador que devuelve un `Resultado`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import streamlit as st

from cuentasclaras.controladores import (
    ControladorAdmin,
    ControladorCompras,
    ControladorCuenta,
    ControladorGastos,
    ControladorHogar,
    ControladorPlanes,
    ControladorResumen,
    ControladorSesion,
    Resultado,
)
from cuentasclaras.modelos import archivos as medios_mod
from cuentasclaras.modelos import cifrado as cifrado_mod
from cuentasclaras.modelos import planes
from cuentasclaras.modelos.almacen import ErrorAlmacen, Store
from cuentasclaras.modelos.configuracion import Config, armar
from cuentasclaras.modelos.dinero import formatear, formatear_corto, hoy, nombre_mes
from cuentasclaras.modelos.fabrica import abrir_almacen
from cuentasclaras.modelos.repositorio import Repositorio

COOKIE = "cc_sesion"
COLOR = "#0f766e"


# --------------------------------------------------------------------------- #
# Configuración y contexto
# --------------------------------------------------------------------------- #
def leer_secretos() -> dict[str, Any]:
    try:
        return dict(st.secrets)
    except Exception:  # noqa: BLE001 - sin secrets.toml no debe romper
        return {}


@dataclass
class Contexto:
    """Contexto de una ejecución: modelo, controladores y sesión activa."""

    config: Config
    store: Store
    repo: Repositorio
    medios: medios_mod.Medios
    ctrl: Any = None
    usuario: dict[str, Any] | None = None
    token: str = ""
    hogar: dict[str, Any] | None = None
    origen_clave: str = ""
    aviso_medios: str = ""

    # --- controladores ---------------------------------------------------- #
    def _base(self, clase):
        return clase(self.repo, self.config, self.medios, self.usuario, self.hogar)

    def sesion(self) -> ControladorSesion:
        return self._base(ControladorSesion)

    def gastos(self) -> ControladorGastos:
        return self._base(ControladorGastos)

    def compras(self) -> ControladorCompras:
        return self._base(ControladorCompras)

    def hogar_ctl(self) -> ControladorHogar:
        return self._base(ControladorHogar)

    def cuenta(self) -> ControladorCuenta:
        return self._base(ControladorCuenta)

    def resumen(self) -> ControladorResumen:
        return self._base(ControladorResumen)

    def planes(self) -> ControladorPlanes:
        return self._base(ControladorPlanes)

    def admin(self) -> ControladorAdmin:
        return self._base(ControladorAdmin)

    # --- atajos ----------------------------------------------------------- #
    @property
    def nombre(self) -> str:
        return (self.usuario or {}).get("nombre") or ""

    @property
    def es_admin(self) -> bool:
        return bool((self.usuario or {}).get("es_admin_plataforma"))

    def dinero(self, valor: Any) -> str:
        return formatear(valor, self.config.simbolo)

    def dinero_corto(self, valor: Any) -> str:
        return formatear_corto(valor, self.config.simbolo)

    def exigir_hogar(self) -> dict[str, Any]:
        if not self.hogar:
            st.stop()
        return self.hogar

    def aviso_cifrado(self) -> str:
        """Mensaje si los datos se están guardando sin cifrar."""
        if self.origen_clave == "" and self.config.cifrado:
            return (
                "Los datos se están guardando **sin cifrar**: agregá `clave_cifrado` "
                "en los secretos para activar el cifrado ChaCha20."
            )
        return ""


# --------------------------------------------------------------------------- #
# Cookies (persistencia de la sesión entre recargas)
# --------------------------------------------------------------------------- #
def _cookie_controller():
    try:
        from streamlit_cookies_controller import CookieController

        return CookieController()
    except Exception:  # noqa: BLE001
        return None


def _leer_cookie(ctrl, clave: str, intentos: int = 6) -> str:
    if ctrl is None:
        return ""
    for intento in range(intentos):
        try:
            valor = ctrl.get(clave)
        except Exception:  # noqa: BLE001
            return ""
        if valor:
            return str(valor)
        if intento < intentos - 1:
            time.sleep(0.15)
    return ""


def _guardar_cookie(ctrl, clave: str, valor: str) -> None:
    if ctrl is None:
        return
    try:
        ctrl.set(clave, valor)
    except Exception:  # noqa: BLE001 - navegador sin cookies
        pass


def _borrar_cookie(ctrl, clave: str) -> None:
    if ctrl is None:
        return
    try:
        ctrl.remove(clave)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #
def _almacen(config: Config) -> tuple[Store, str]:
    if "cc_store" not in st.session_state:
        store, origen = abrir_almacen(config)
        st.session_state["cc_store"] = store
        st.session_state["cc_origen_clave"] = origen
    return st.session_state["cc_store"], st.session_state.get("cc_origen_clave", "")


def arrancar() -> Contexto:
    """Arma el contexto de la ejecución actual (una vez por rerun)."""
    config = armar(leer_secretos())

    try:
        store, origen_clave = _almacen(config)
    except cifrado_mod.ErrorCifrado as exc:
        st.error(
            "No se pudieron descifrar los datos guardados.\n\n"
            f"**Detalle:** {exc}\n\n"
            "Revisá que `clave_cifrado` sea la misma con la que se guardaron los datos."
        )
        st.stop()
        raise
    except ErrorAlmacen as exc:
        st.error(
            "No pudimos conectarnos al almacenamiento.\n\n"
            f"**Detalle técnico:** {exc}\n\n"
            "Revisá `gcp_service_account` y `sheet_url_gastos`, o corré en modo demo "
            "con `CUENTASCLARAS_DEMO=1`."
        )
        st.stop()
        raise

    repo = Repositorio(store, config)
    _sembrar_demo(store, config, repo)
    aviso_medios = ""
    try:
        medios = medios_mod.construir(config)
    except Exception as exc:  # noqa: BLE001 - sin comprobantes la app sigue andando
        aviso_medios = (
            f"No se pudieron configurar los comprobantes ({exc}). "
            "Las imágenes se van a guardar en el disco del servidor."
        )
        medios = medios_mod.MediosLocal(config.medios_dir)

    ctx = Contexto(
        config=config,
        store=store,
        repo=repo,
        medios=medios,
        ctrl=_cookie_controller(),
        origen_clave=origen_clave,
        aviso_medios=aviso_medios,
    )
    _restaurar(ctx)
    _resolver_hogar(ctx)
    return ctx


def _sembrar_demo(store: Store, config: Config, repo: Repositorio) -> None:
    """Con `CUENTASCLARAS_DEMO=1` y base vacía, carga datos de ejemplo."""
    import os

    valor = (os.environ.get("CUENTASCLARAS_DEMO") or "").strip().lower()
    if valor not in {"1", "si", "sí", "true", "on"}:
        return
    if config.almacen == "sheets":
        return
    try:
        if store.all("usuarios"):
            return
        from cuentasclaras.modelos import datos_demo

        datos_demo.sembrar(repo)
    except Exception:  # noqa: BLE001 - la demo nunca debe romper el arranque
        pass


def _restaurar(ctx: Contexto) -> None:
    if st.session_state.get("cc_usuario_id"):
        usuario = ctx.repo.usuario(st.session_state["cc_usuario_id"])
        if usuario and usuario.get("activo_booleano"):
            ctx.usuario = usuario
            ctx.token = st.session_state.get("cc_token", "")
            return
        for clave in ("cc_usuario_id", "cc_token", "cc_hogar_id"):
            st.session_state.pop(clave, None)

    token = _leer_cookie(ctx.ctrl, COOKIE)
    if not token:
        return
    resultado = ctx.sesion().restaurar(token)
    if not resultado.ok:
        _borrar_cookie(ctx.ctrl, COOKIE)
        return
    datos = resultado.datos or {}
    st.session_state["cc_usuario_id"] = datos["usuario"]["id"]
    st.session_state["cc_token"] = token
    if datos.get("hogar_activo"):
        st.session_state["cc_hogar_id"] = datos["hogar_activo"]
    ctx.usuario = datos["usuario"]
    ctx.token = token


def _resolver_hogar(ctx: Contexto) -> None:
    if not ctx.usuario:
        return
    hogares = ctx.repo.hogares_de(ctx.usuario["id"])
    if not hogares:
        return
    preferido = st.session_state.get("cc_hogar_id")
    elegido = next((h for h in hogares if h["id"] == preferido), None) or hogares[0]
    st.session_state["cc_hogar_id"] = elegido["id"]
    ctx.hogar = elegido


# --------------------------------------------------------------------------- #
# Acciones de sesión
# --------------------------------------------------------------------------- #
def entrar(ctx: Contexto, datos: dict[str, Any]) -> None:
    """Guarda la sesión creada por el controlador y recarga."""
    usuario = datos["usuario"]
    token = datos["token"]
    st.session_state["cc_usuario_id"] = usuario["id"]
    st.session_state["cc_token"] = token
    st.session_state.pop("cc_hogar_id", None)
    _guardar_cookie(ctx.ctrl, COOKIE, token)
    st.rerun()


def salir(ctx: Contexto) -> None:
    token = st.session_state.get("cc_token") or _leer_cookie(ctx.ctrl, COOKIE, intentos=1)
    if token:
        ctx.sesion().cerrar(token)
    _borrar_cookie(ctx.ctrl, COOKIE)
    for clave in ("cc_usuario_id", "cc_token", "cc_hogar_id", "cc_store", "cc_origen_clave"):
        st.session_state.pop(clave, None)
    st.rerun()


def cambiar_hogar(ctx: Contexto, hogar_id: str) -> None:
    st.session_state["cc_hogar_id"] = hogar_id
    token = st.session_state.get("cc_token", "")
    if token:
        ctx.sesion().elegir_hogar(token, hogar_id)
    st.rerun()


# --------------------------------------------------------------------------- #
# Feedback de resultados
# --------------------------------------------------------------------------- #
def mostrar(resultado: Resultado) -> None:
    if resultado.tipo == "error":
        st.error(resultado.mensaje)
    elif resultado.tipo == "aviso":
        st.warning(resultado.mensaje)


def aplicar(resultado: Resultado, recargar: bool = True) -> bool:
    """Muestra el resultado y recarga la página si salió bien."""
    if not resultado.ok:
        st.error(resultado.mensaje)
        return False
    if resultado.tipo == "aviso":
        st.warning(resultado.mensaje)
    elif resultado.mensaje:
        st.toast(resultado.mensaje, icon="✅")
    if recargar:
        st.rerun()
    return True


def ejecutar(accion: Callable[[], Resultado], recargar: bool = True) -> bool:
    """Ejecuta una acción mostrando el spinner y el resultado."""
    with st.spinner("Guardando..."):
        resultado = accion()
    return aplicar(resultado, recargar=recargar)


# --------------------------------------------------------------------------- #
# Estilos y componentes
# --------------------------------------------------------------------------- #
def css() -> None:
    st.markdown(
        """
        <style>
        .cc-hero { padding: 1.2rem 1.4rem; border-radius: 18px;
                   background: linear-gradient(135deg,#0f766e 0%,#134e4a 60%,#0f172a 100%);
                   color:#f8fafc; margin-bottom: 1rem; }
        .cc-hero h1 { color:#fff; margin:0 0 .2rem 0; font-size: 2.1rem; }
        .cc-hero p { color:#d1fae5; margin:0; font-size:1.02rem; }
        .cc-card { border:1px solid #e2e8f0; border-radius:14px; padding:1rem 1.1rem;
                   background:#fff; box-shadow:0 1px 2px rgba(15,23,42,.04); height:100%; }
        .cc-card h4 { margin:.1rem 0 .35rem 0; font-size:1rem; color:#0f172a; }
        .cc-card p { margin:0; color:#475569; font-size:.9rem; }
        .cc-pill { display:inline-block; padding:.12rem .55rem; border-radius:999px;
                   background:#ccfbf1; color:#115e59; font-size:.76rem; font-weight:600; }
        .cc-pill-gris { background:#e2e8f0; color:#334155; }
        .cc-precio { font-size:2rem; font-weight:800; color:#0f172a; }
        .cc-tachado { text-decoration: line-through; color:#94a3b8; font-size:.9rem; }
        .cc-nota { color:#64748b; font-size:.82rem; }
        .cc-codigo { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                     font-size:1.35rem; letter-spacing:.28rem; font-weight:700;
                     background:#f1f5f9; border-radius:10px; padding:.45rem .8rem;
                     display:inline-block; }
        div[data-testid="stMetricValue"] { font-size: 1.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def tarjeta(titulo: str, texto: str, icono: str = "") -> str:
    return f'<div class="cc-card"><h4>{icono} {titulo}</h4><p>{texto}</p></div>'


def pill(texto: str, gris: bool = False) -> str:
    clase = "cc-pill cc-pill-gris" if gris else "cc-pill"
    return f'<span class="{clase}">{texto}</span>'


def encabezado(titulo: str, subtitulo: str = "", icono: str = "") -> None:
    st.markdown(
        f'<div class="cc-hero"><h1>{icono} {titulo}</h1><p>{subtitulo}</p></div>',
        unsafe_allow_html=True,
    )


def pie() -> None:
    st.markdown("---")
    st.markdown(
        '<div class="cc-nota">Cuentas Claras · gastos compartidos sin discusiones · '
        "hecho en Argentina 🇦🇷</div>",
        unsafe_allow_html=True,
    )


def sin_hogar(ctx: Contexto) -> None:
    """Onboarding: crear el primer hogar o entrar con un código."""
    encabezado(
        "Creá tu hogar",
        "Un hogar agrupa los gastos de una casa: pareja, familia o compañeros.",
        "🏡",
    )
    col_crear, col_unir = st.columns(2, gap="large")
    with col_crear:
        st.subheader("Empezar de cero")
        with st.form("crear_hogar"):
            nombre = st.text_input("Nombre del hogar", placeholder="Casa San Pedro")
            enviado = st.form_submit_button(
                "Crear hogar", type="primary", use_container_width=True
            )
        if enviado:
            resultado = ctx.hogar_ctl().crear(nombre)
            if resultado.ok:
                st.session_state["cc_hogar_id"] = (resultado.datos or {}).get("id", "")
                aplicar(resultado)
            else:
                mostrar(resultado)
    with col_unir:
        st.subheader("Me invitaron")
        with st.form("unir_hogar"):
            codigo = st.text_input("Código de invitación", placeholder="ABC123")
            enviado2 = st.form_submit_button("Unirme", use_container_width=True)
        if enviado2:
            resultado = ctx.sesion().unirse(ctx.usuario["id"], codigo)
            if resultado.ok:
                st.session_state["cc_hogar_id"] = (resultado.datos or {}).get("id", "")
                aplicar(resultado)
            else:
                mostrar(resultado)
    st.caption(
        "Podés pertenecer a más de un hogar (por ejemplo, tu casa y la de un familiar) "
        "y cambiar entre ellos desde la barra lateral."
    )


def formato_mes(clave: str) -> str:
    return nombre_mes(clave) if clave else "Histórico completo"


__all__ = [
    "COOKIE",
    "COLOR",
    "Contexto",
    "Resultado",
    "aplicar",
    "arrancar",
    "cambiar_hogar",
    "css",
    "ejecutar",
    "encabezado",
    "entrar",
    "formato_mes",
    "hoy",
    "leer_secretos",
    "mostrar",
    "pie",
    "pill",
    "planes",
    "salir",
    "sin_hogar",
    "tarjeta",
]
