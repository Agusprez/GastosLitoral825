# Operación y mantenimiento

## Rutinas

| Cuándo | Qué |
| --- | --- |
| Semanal | Mirar el panel de plataforma (altas, hogares Pro, errores reportados). |
| Mensual | Backup del hogar propio y de un hogar de cliente al azar (probar que el JSON abra). |
| Mensual | Revisar hogares que tocaron el límite del plan (señal de upgrade). |
| Trimestral | Revisar cuentas deshabilitadas y sesiones huérfanas. |

## Backups

**Con Google Sheets**

1. *Hogar → Ajustes → Respaldo completo (JSON)* por hogar (o `exportar_json`).
2. Copia de la planilla: *Archivo → Hacer una copia* (queda en tu Drive).
3. Guardá además `clave_cifrado` en el gestor de contraseñas. Sin ella, el backup de
   la planilla no sirve.

**Con SQLite / VPS**

```bash
sqlite3 data/cuentasclaras.db ".backup '/backups/cc-$(date +%F).db'"
tar czf /backups/comprobantes-$(date +%F).tgz data/comprobantes
cp data/clave.key /backups/clave-$(date +%F).key   # ¡protegida!
```

## Clave de cifrado

* **Nunca** la cambies sin re-cifrar: los datos viejos quedarían ilegibles y la app
  mostraría "No se pudieron descifrar los datos".
* Rotación (procedimiento manual):
  1. Backup completo (JSON por hogar) con la clave actual.
  2. Poné la clave nueva en los secretos.
  3. Creá un almacén vacío (pestañas nuevas) e importá el JSON/CSV con un script.
     Alternativa rápida: escribir un `tools/recifrar.py` que lea con la clave vieja
     y escriba con la nueva usando dos `Cifrador` distintos (la interfaz `Store` lo
     permite envolviendo el mismo backend).
* Si se perdió la clave: los datos cifrados no se recuperan. Queda reiniciar el
  servicio con una clave nueva (empezar de cero o re-importar el último backup en
  claro, si existe).

## Incidentes

| Situación | Pasos |
| --- | --- |
| Cuenta comprometida | Panel de plataforma → deshabilitar (cierra todas las sesiones). Avisar a la persona y pedir cambio de contraseña antes de rehabilitar. |
| Persona que se va del hogar | El propietario la quita desde *Hogar → Personas*. Sus gastos quedan (a nombre de ella) para no descuadrar los saldos. |
| Hogar con datos equivocados | Se pueden editar o anular gastos desde el detalle. Anular conserva el rastro en actividad. |
| Plan Pro no activado | Verificar la transferencia y activarlo desde *Plataforma → Hogares*. |
| Cuota de Google Sheets | Esperar 1 minuto; la app cachea lecturas 5 s. Si es recurrente, bajar la frecuencia de refresco o migrar a Postgres. |
| Datos borrados por error | Restaurar la copia de la planilla (Drive → Historial de versiones) o re-importar el JSON del backup. |

## Costos de referencia

| Servicio | Costo |
| --- | --- |
| Streamlit Community Cloud | Gratis (con límites y sin SLA) |
| Google Sheets | Gratis hasta 10 M de celdas |
| Google Drive (comprobantes) | 15 GB gratis con la cuenta de la service account |
| Dominio | ~USD 10/año |
| VPS chico (si se usa) | ~USD 5/mes |

Con 10 hogares Pro ($4.900/mes cada uno) el servicio cubre infraestructura, dominio
y sobra margen; el costo variable es prácticamente cero.

## Soporte

* Alta de código de invitación: lo hace cada hogar desde *Hogar → Invitaciones*.
* Recuperar contraseña: no hay email automático. Verificá identidad (email + última
  actividad) y cambiá la contraseña desde el panel de plataforma cuando exista la
  función; hoy se resuelve con un script que actualiza `hash_clave`:

```python
from cuentasclaras.modelos import autenticacion as auth
usuario = repo.usuario_por_email("ana@x.com")
repo.store.update("usuarios", usuario["id"], {"hash_clave": auth.hash_clave("NuevaClave2026")})
auth.revocar_todas(repo.store, usuario["id"])
```

## Métricas que importan

Del panel de plataforma:

* **Altas** (usuarios y hogares) → crecimiento.
* **Hogares activos en 30 días** → retención real.
* **Hogares Pro / MRR** → ingresos.
* **Gastos cargados** → uso efectivo del producto (un hogar con 0 gastos se va).
