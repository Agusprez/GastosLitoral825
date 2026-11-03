"""Capa de vista (V de MVC): pantallas Streamlit.

* `componentes`  — arranque de sesión, estilos y helpers compartidos.
* `navegacion`   — barra lateral con hogar activo y secciones.
* `landing`      — página pública con planes y formularios de acceso.
* `inicio`       — tablero del período (balance, gráfico, últimos movimientos).
* `gastos`       — alta, listado con filtros y detalle editable.
* `compras`      — lista de compras compartida.
* `hogar`        — personas, invitaciones, ajustes y actividad.
* `cuenta`       — perfil, contraseña y baja.
* `planes`       — estado de la suscripción y pedido de upgrade.
* `admin`        — panel de plataforma (métricas, planes, estado técnico).

Ninguna vista importa el almacén ni ejecuta reglas: siempre pasa por un
controlador de `cuentasclaras.controladores`, que devuelve un `Resultado`.
"""
