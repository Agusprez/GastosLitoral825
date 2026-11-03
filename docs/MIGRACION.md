# Migrar los datos de la versión 1

La v1 guardaba todo en una planilla con dos pestañas:

* `Gastos` → `Fecha, Quien, Concepto, Monto, Categoria, Comprobante`
* `Lista_Compras` → `Elemento, Quién Anotó, Comprado, Fecha Anotado`

La v2 escribe en **pestañas nuevas** (`cc_usuarios`, `cc_gastos`, …) dentro de la
**misma** planilla. Las pestañas viejas no se tocan: se pueden quedar como respaldo
o borrarse cuando confirmes que todo migró.

## Antes de empezar

1. **Copia la planilla** (Archivo → Hacer una copia) o descargá un CSV de `Gastos`.
2. Configurá los secretos de la v2 (ver `docs/DEPLOY.md`) y una `clave_cifrado`.
3. Decidí quiénes son las personas y con qué email van a entrar.

## Importar desde la planilla

```bash
# 1) Informe: no escribe nada
python tools/importar_planilla.py \
  --usuarios "Agustin=agustin@ejemplo.com,Jorge=jorge@ejemplo.com" \
  --hogar "Casa San Pedro"

# 2) Importación real
python tools/importar_planilla.py \
  --usuarios "Agustin=agustin@ejemplo.com,Jorge=jorge@ejemplo.com" \
  --hogar "Casa San Pedro" --aplicar
```

Qué hace:

* Crea las cuentas que no existan (contraseña tomada de `--claves` o de la sección
  `passwords` de los secretos de la v1, si sigue estando). Si la cuenta ya existe,
  la usa y no toca su contraseña.
* Crea el hogar, agrega a las personas y pasa el hogar a Pro **durante** la
  importación (para no chocar con el límite de 200 gastos/mes) y lo deja en el plan
  que indiques con `--plan` (por defecto `gratis`).
* Importa los gastos repartidos en partes iguales entre las personas del hogar, que
  es la regla que usaba la v1 ("mitad y mitad" al cerrar el mes).
* Conserva los links de comprobantes de la v1 tal cual (se muestran, no se
  descargan).
* Anota las compras pendientes de `Lista_Compras`.
* Informa filas omitidas con el motivo (fecha inválida, persona desconocida, etc.).

> La v1 no guardaba el `id` de Google Sheets ni quién había cargado cada gasto, así
> que en la v2 esos gastos quedan a nombre de la persona que pagó.

## Importar desde un CSV

```bash
python tools/importar_planilla.py --origen csv --csv gastos.csv \
  --compras-csv compras.csv \
  --usuarios "Agustin=agustin@ejemplo.com,Jorge=jorge@ejemplo.com" \
  --hogar "Casa San Pedro" --aplicar
```

El CSV puede venir de Google Sheets (Archivo → Descargar → CSV) o del export de la
v1. Se aceptan encabezados con mayúsculas, acentos o variantes:
`Fecha/fecha`, `Quién pagó/quien`, `Detalle/concepto/descripcion`, `Monto/importe`,
`Categoría/categoria`, `Comprobante/ticket`.

## Verificar la migración

1. Entrá con una de las cuentas creadas.
2. *Inicio → Histórico completo*: compará el total con la suma de la planilla vieja.
3. *Gastos*: buscá un par de movimientos conocidos y revisá montos y fechas.
4. *Hogar → Actividad*: no debería haber errores raros.
5. Exportá el CSV de un mes y comparalo con la pestaña `Gastos` filtrada por ese mes.

Si algo no coincide, borrá las pestañas `cc_*` (la planilla vieja sigue intacta) y
volvé a correr el importador.

## Cifrar lo que ya estaba guardado

Si importaste con el cifrado activo, no hay nada que hacer: todo entra cifrado. Si
activaste la clave **después** de tener datos:

```bash
python tools/cifrar_existente.py            # informe
python tools/cifrar_existente.py --aplicar  # cifra
```

## Volver atrás

La v2 no modifica las pestañas viejas, así que la v1 sigue funcionando con la misma
planilla. Para volver: desplegá `legacy/app_v1.py` con los secretos de la v1 y listo
(no verá los datos nuevos, que están en `cc_*`).
