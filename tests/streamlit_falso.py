"""Doble de prueba de Streamlit.

En este entorno no hay red para instalar Streamlit, así que las vistas se
prueban contra este módulo: replica las firmas que usa la app y hace fallar el
test si se pasa un parámetro que Streamlit no acepta (así se detectan typos).

No pretende ser Streamlit: no renderiza nada, sólo ejecuta el código de la vista
y devuelve valores por defecto razonables.
"""

from __future__ import annotations

import io
import sys
import types
from typing import Any, Iterable


class RerunStop(BaseException):
    """Se lanza para cortar la ejecución, como hace `st.rerun()`."""


class StopAplicacion(BaseException):
    """Como `st.stop()`."""


class _Estado(dict):
    def __getattr__(self, nombre: str) -> Any:
        try:
            return self[nombre]
        except KeyError as exc:  # pragma: no cover
            raise AttributeError(nombre) from exc

    def __setattr__(self, nombre: str, valor: Any) -> None:
        self[nombre] = valor


class _Secretos(dict):
    def __getattr__(self, nombre: str) -> Any:
        try:
            return self[nombre]
        except KeyError as exc:
            raise AttributeError(nombre) from exc


class _Seleccion:
    def __init__(self, filas: list[int] | None = None) -> None:
        self.rows = filas or []


class _Evento:
    def __init__(self, filas: list[int] | None = None) -> None:
        self.selection = _Seleccion(filas)


class _Contenedor:
    """Sirve de contexto (`with st.form(...)`) y de contenedor de widgets."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.salida: list[Any] = []

    def __enter__(self) -> "_Contenedor":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    # Un contenedor también expone widgets (por ejemplo `st.sidebar.button`).
    def __getattr__(self, nombre: str) -> Any:
        return globals().get(nombre, _noop)


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


class _BarraLateral(_Contenedor):
    pass


# Estado global del doble ---------------------------------------------------- #
ESTADO = _Estado()
SECRETOS = _Secretos()
SESION_COOKIES: dict[str, str] = {}
MODO_CLICK = False  # si es True, botones y submits devuelven True
ARCHIVO_SUBIDO: Any = None  # lo que debe devolver `file_uploader`
PEDIDOS: list[tuple[str, tuple, dict]] = []  # registro de llamadas


def _registrar(nombre: str, args: tuple, kwargs: dict) -> None:
    PEDIDOS.append((nombre, args, kwargs))


def falso_config(**kwargs: Any) -> None:
    """Reinicia el doble y ajusta opciones del test."""
    global MODO_CLICK, ARCHIVO_SUBIDO
    MODO_CLICK = bool(kwargs.get("modo_click", False))
    ARCHIVO_SUBIDO = kwargs.get("archivo")
    ESTADO.clear()
    SECRETOS.clear()
    SESION_COOKIES.clear()
    COOKIE_LLAMADAS.clear()
    PEDIDOS.clear()


def llamadas(nombre: str) -> list[tuple[tuple, dict]]:
    return [(a, k) for (n, a, k) in PEDIDOS if n == nombre]


# Configuración ---------------------------------------------------------------- #
def set_page_config(**kwargs: Any) -> None:
    _registrar("set_page_config", (), kwargs)


# Presentación ----------------------------------------------------------------- #
def markdown(body: Any = "", unsafe_allow_html: bool = False) -> None:
    _registrar("markdown", (body,), {"unsafe_allow_html": unsafe_allow_html})


def title(body: Any = "", **kwargs: Any) -> None:
    _registrar("title", (body,), kwargs)


def header(body: Any = "", **kwargs: Any) -> None:
    _registrar("header", (body,), kwargs)


def subheader(body: Any = "", **kwargs: Any) -> None:
    _registrar("subheader", (body,), kwargs)


def caption(body: Any = "", **kwargs: Any) -> None:
    _registrar("caption", (body,), kwargs)


def write(*args: Any, **kwargs: Any) -> None:
    _registrar("write", args, kwargs)


def text(body: Any = "", **kwargs: Any) -> None:
    _registrar("text", (body,), kwargs)


def code(body: Any = "", **kwargs: Any) -> None:
    _registrar("code", (body,), kwargs)


def divider() -> None:
    _registrar("divider", (), {})


def progress(valor: float = 0.0, text: str | None = None) -> None:
    _registrar("progress", (valor,), {"text": text})


def metric(
    label: str,
    value: Any,
    delta: Any = None,
    help: str | None = None,
    delta_color: str = "normal",
) -> None:
    _registrar("metric", (label, value), {"delta": delta, "delta_color": delta_color})


def image(image: Any, caption: str | None = None, use_container_width: bool = False, **kwargs: Any) -> None:
    _registrar("image", (image,), {"caption": caption, "use_container_width": use_container_width})


def pyplot(figura: Any = None, **kwargs: Any) -> None:
    _registrar("pyplot", (figura,), kwargs)


def dataframe(
    data: Any = None,
    use_container_width: bool = False,
    hide_index: bool | None = None,
    selection_mode: str | None = None,
    on_select: str = "ignore",
    key: str | None = None,
) -> _Evento:
    _registrar("dataframe", (data,), {"key": key, "on_select": on_select})
    return _Evento([])


def table(data: Any = None, **kwargs: Any) -> None:
    _registrar("table", (data,), kwargs)


def json(body: Any, **kwargs: Any) -> None:
    _registrar("json", (body,), kwargs)


# Mensajes ---------------------------------------------------------------------- #
def success(body: str = "", **kwargs: Any) -> None:
    _registrar("success", (body,), kwargs)


def error(body: str = "", **kwargs: Any) -> None:
    _registrar("error", (body,), kwargs)


def warning(body: str = "", **kwargs: Any) -> None:
    _registrar("warning", (body,), kwargs)


def info(body: str = "", **kwargs: Any) -> None:
    _registrar("info", (body,), kwargs)


def toast(body: str = "", icon: str | None = None) -> None:
    _registrar("toast", (body,), {"icon": icon})


def balloons() -> None:
    _registrar("balloons", (), {})


# Controles ---------------------------------------------------------------------- #
def button(
    label: str = "",
    key: str | None = None,
    help: str | None = None,
    type: str = "secondary",
    use_container_width: bool = False,
    disabled: bool = False,
    on_click: Any = None,
) -> bool:
    _registrar("button", (label,), {"key": key})
    return MODO_CLICK


def download_button(
    label: str = "",
    data: Any = None,
    file_name: str | None = None,
    mime: str | None = None,
    use_container_width: bool = False,
    key: str | None = None,
) -> bool:
    _registrar("download_button", (label,), {"file_name": file_name, "key": key})
    return MODO_CLICK


def link_button(
    label: str = "",
    url: str = "",
    use_container_width: bool = False,
    help: str | None = None,
) -> None:
    _registrar("link_button", (label, url), {"use_container_width": use_container_width})


def checkbox(label: str = "", value: bool = False, key: str | None = None, help: str | None = None) -> bool:
    _registrar("checkbox", (label,), {"key": key})
    return value or MODO_CLICK


def toggle(label: str = "", value: bool = False, key: str | None = None, help: str | None = None) -> bool:
    _registrar("toggle", (label,), {"key": key})
    return value


def radio(
    label: str = "",
    options: Iterable[Any] = (),
    index: int = 0,
    format_func: Any = None,
    key: str | None = None,
    label_visibility: str = "visible",
) -> Any:
    opciones = list(options)
    _registrar("radio", (label,), {"key": key})
    if not opciones:
        return None
    return opciones[index if 0 <= index < len(opciones) else 0]


def selectbox(
    label: str = "",
    options: Iterable[Any] = (),
    index: int = 0,
    format_func: Any = None,
    key: str | None = None,
    help: str | None = None,
    label_visibility: str = "visible",
) -> Any:
    opciones = list(options)
    _registrar("selectbox", (label,), {"key": key})
    if not opciones:
        return None
    return opciones[index if 0 <= index < len(opciones) else 0]


def multiselect(
    label: str = "",
    options: Iterable[Any] = (),
    default: Any = None,
    format_func: Any = None,
    key: str | None = None,
    help: str | None = None,
) -> list[Any]:
    _registrar("multiselect", (label,), {"key": key})
    if default is not None:
        return list(default)
    return list(options)


def text_input(
    label: str = "",
    value: str = "",
    placeholder: str | None = None,
    help: str | None = None,
    type: str = "default",
    key: str | None = None,
    label_visibility: str = "visible",
) -> str:
    _registrar("text_input", (label,), {"key": key})
    return value


def text_area(
    label: str = "",
    value: str = "",
    placeholder: str | None = None,
    help: str | None = None,
    key: str | None = None,
) -> str:
    _registrar("text_area", (label,), {"key": key})
    return value


def number_input(
    label: str = "",
    min_value: Any = None,
    max_value: Any = None,
    value: Any = None,
    step: Any = None,
    format: str | None = None,
    key: str | None = None,
    help: str | None = None,
) -> Any:
    _registrar("number_input", (label,), {"key": key})
    if value is not None:
        return value
    return min_value if min_value is not None else 0


def date_input(
    label: str = "",
    value: Any = None,
    min_value: Any = None,
    max_value: Any = None,
    format: str = "YYYY/MM/DD",
    key: str | None = None,
) -> Any:
    _registrar("date_input", (label,), {"key": key})
    return value


def file_uploader(label: str = "", type: Any = None, accept_multiple_files: bool = False, key: str | None = None) -> Any:
    _registrar("file_uploader", (label,), {"key": key})
    return ARCHIVO_SUBIDO


def slider(label: str = "", min_value: Any = 0, max_value: Any = 100, value: Any = None, key: str | None = None) -> Any:
    return value if value is not None else min_value


def color_picker(label: str = "", value: str = "#000000", key: str | None = None) -> str:
    return value


# Layout ------------------------------------------------------------------------ #
def columns(spec: Any, gap: str = "small", **kwargs: Any) -> list[_Contenedor]:
    cantidad = spec if isinstance(spec, int) else len(spec)
    _registrar("columns", (spec,), {"gap": gap})
    return [_Contenedor() for _ in range(max(cantidad, 1))]


def tabs(labels: Iterable[str]) -> list[_Contenedor]:
    _registrar("tabs", (list(labels),), {})
    return [_Contenedor() for _ in labels]


def expander(label: str = "", expanded: bool = False, **kwargs: Any) -> _Contenedor:
    _registrar("expander", (label,), {"expanded": expanded})
    return _Contenedor()


def container(border: bool = False, **kwargs: Any) -> _Contenedor:
    return _Contenedor()


def form(key: str = "", clear_on_submit: bool = False, border: bool = True) -> _Contenedor:
    _registrar("form", (key,), {"clear_on_submit": clear_on_submit})
    return _Contenedor()


def form_submit_button(
    label: str = "Submit",
    type: str = "secondary",
    use_container_width: bool = False,
    disabled: bool = False,
) -> bool:
    _registrar("form_submit_button", (label,), {})
    return MODO_CLICK


def spinner(text: str = "Loading...", **kwargs: Any) -> _Contenedor:
    return _Contenedor()


def empty() -> _Contenedor:
    return _Contenedor()


def dialog(title: str = "", width: str = "small", **kwargs: Any):
    """Decorador que en el doble ejecuta el cuerpo directamente."""

    def decorador(funcion):
        def envoltura(*args: Any, **kwargs2: Any):
            return funcion(*args, **kwargs2)

        return envoltura

    return decorador


def cache_data(*args: Any, **kwargs: Any):
    def decorador(funcion):
        funcion.clear = lambda: None
        return funcion

    return decorador


def cache_resource(*args: Any, **kwargs: Any):
    def decorador(funcion):
        funcion.clear = lambda: None
        return funcion

    return decorador


def rerun(*args: Any, **kwargs: Any) -> None:
    raise RerunStop()


def stop(*args: Any, **kwargs: Any) -> None:
    raise StopAplicacion()


def switch_page(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    raise RerunStop()


def query_params() -> dict[str, Any]:  # pragma: no cover
    return {}


def sidebar() -> _BarraLateral:  # pragma: no cover - se reemplaza abajo
    return _BarraLateral()


# Fake de los componentes de cookies --------------------------------------------- #
COOKIE_LLAMADAS: list[tuple[str, str, str]] = []


class _CookieController:
    """Imita al componente: `set`/`remove` se aplican al "navegador" (SESION_COOKIES)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def get(self, clave: str) -> str | None:
        return SESION_COOKIES.get(clave)

    def set(self, clave: str, valor: str, **opciones: Any) -> None:
        SESION_COOKIES[clave] = valor
        COOKIE_LLAMADAS.append(("set", clave, str(valor)))

    def remove(self, clave: str) -> None:
        SESION_COOKIES.pop(clave, None)
        COOKIE_LLAMADAS.append(("remove", clave, ""))

    def getAll(self) -> dict[str, str]:  # noqa: N802 - API del paquete real
        return dict(SESION_COOKIES)


def instalar() -> types.ModuleType:
    """Registra el módulo en `sys.modules` (idempotente)."""
    modulo = sys.modules.get("streamlit")
    if modulo is not None and getattr(modulo, "es_falso", False):
        return modulo

    modulo = types.ModuleType("streamlit")
    modulo.es_falso = True
    for nombre, valor in list(globals().items()):
        if nombre.startswith("_") or nombre in {
            "instalar",
            "falso_config",
            "llamadas",
            "Any",
            "Iterable",
            "io",
            "sys",
            "types",
        }:
            continue
        setattr(modulo, nombre, valor)

    modulo.session_state = ESTADO
    modulo.secrets = SECRETOS
    modulo.sidebar = _BarraLateral()
    sys.modules["streamlit"] = modulo

    cookies = types.ModuleType("streamlit_cookies_controller")
    cookies.CookieController = _CookieController
    sys.modules["streamlit_cookies_controller"] = cookies

    return modulo
