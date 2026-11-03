"""Modelo: entidades, persistencia, reglas de negocio y cifrado.

Módulos
-------
* `configuracion`  — parámetros de despliegue (secretos + entorno).
* `dinero`         — fechas, montos y formato es-AR.
* `almacen`        — implementaciones de persistencia (Google Sheets / SQLite / RAM).
* `cifrado`        — cifrado autenticado de los datos guardados.
* `fabrica`        — arma el almacén con cifrado.
* `autenticacion`  — hash de contraseñas, sesiones y bloqueo por intentos.
* `saldos`         — división de gastos y cálculo de deudas.
* `planes`         — planes comerciales y límites.
* `archivos`       — comprobantes privados (disco o Drive).
* `repositorio`    — reglas de negocio y control de acceso por hogar.
* `datos_demo`     — datos de ejemplo para la demo.

La importación es perezosa a propósito: importar el paquete no arrastra todo el
modelo (ni siquiera `gspread`), así los tests y los scripts arrancan rápido y sin
dependencias opcionales.
"""

__all__ = [
    "almacen",
    "archivos",
    "autenticacion",
    "cifrado",
    "configuracion",
    "datos_demo",
    "dinero",
    "fabrica",
    "planes",
    "repositorio",
    "saldos",
]
