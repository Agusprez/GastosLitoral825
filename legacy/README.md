# Versión 1 (histórica)

Estos archivos son la app original: un Streamlit de ~450 líneas con **dos usuarios
fijos** (Agustín y Jorge) atados a **una** planilla de Google, contraseñas
comparadas en texto plano contra `st.secrets` y una cookie que guardaba el nombre
del usuario sin firmar.

Se conservan sólo como referencia para entender de dónde venimos y para comparar
comportamientos. **No se despliegan**: el punto de entrada actual es `app.py`
(ver el README de la raíz).

| Archivo | Qué era |
| --- | --- |
| `gastos.py` | Login con cookies + pestañas (cargar gasto, resumen, compras). |
| `resumen.py` | Filtros por mes, deuda entre los dos, gráfico de torta y edición de gastos. |
| `compras.py` | Lista de compras sobre la pestaña `Lista_Compras`. |

Se mantuvieron los nombres originales para que los `import` entre ellos sigan
funcionando si alguien quiere levantarlos en un entorno aparte.

Diferencias principales con la versión 2:

* Usuarios reales (registro, contraseñas con `scrypt`, sesiones en base, bloqueo por
  intentos) y varios hogares por cuenta.
* Aislamiento por hogar verificado en el modelo, no en la interfaz.
* Datos cifrados en reposo (ChaCha20 + HMAC) y comprobantes privados (Drive o
  disco), en lugar de imágenes públicas en imgbb.
* Planes, límites, exportación, auditoría y panel de administración.
* Tests (modelo, controladores, vistas y end-to-end).
