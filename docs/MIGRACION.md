# Migrar los datos de la versión 1

La v1 guardaba todo en una planilla con dos pestañas:

* `Gastos` → `Fecha, Quien, Concepto, Monto, Categoria, Comprobante`
* `Lista_Compras` → `Elemento, Quién Anotó, Comprado, Fecha Anotado`

La v2 escribe en **pestañas nuevas** (`cc_usuarios`, `cc_gastos`, …) dentro de la
**misma** planilla. Las pestañas viejas no se tocan: se pueden quedar como respaldo
o borrarse cuando confirmes que todo migró.

## Opción A (recomendada): subir el archivo, sin tocar nada

Todo ocurre donde ya están las credenciales, y **sin leer la planilla** (no consume
la cuota de lecturas de Google): sólo se escribe una vez, en bloque.

1. En la planilla vieja: *Archivo → Descargar → CSV* de la pestaña `Gastos`
   (o descargá el Excel completo, con las dos pestañas).
2. En la app: elegí el hogar destino (tiene que ser Pro: Gratis permite 200 gastos
   por mes) y andá a *Hogar → Ajustes → **📥 Importar los gastos anteriores***.
3. Subí el CSV o Excel. Vas a ver el resumen: cuántos gastos, el total, el rango de
   fechas y las compras pendientes.
4. Asigná cada nombre de la planilla a la persona del hogar (la app propone las
   coincidencias por nombre y email). Los nombres que no estén se pueden mandar a
   una persona o dejar afuera.
5. Marcá la confirmación y **Importar ahora**.

## Opción B: leer las pestañas viejas de la planilla

Si los datos están en la misma planilla de la app, el panel también las busca
(`Gastos`, `Lista_Compras`, o cualquier pestaña con las columnas `Fecha, Quien,
Concepto, Monto`). Se lee sólo cuando apretás el botón, para no consumir cuota.

Si están en **otra planilla**, agregá su URL en los Secretos:
`hoja_url_legacy = "https://docs.google.com/spreadsheets/d/.../edit"` (la cuenta de
servicio necesita acceso de lectura). La app te muestra qué pestañas ve, para que
puedas confirmar.

## Antes de importar

Detalles:

* La app busca las pestañas por nombre y, si no aparecen, **por sus columnas**
  (`Fecha, Quien, Concepto, Monto`), así las encuentra aunque se llamen «Gastos 2025»
  o estén en otra hoja del mismo archivo.
* Si los datos viejos están en **otra planilla**, agregá su URL en los Secretos como
  `hoja_url_legacy = "https://docs.google.com/spreadsheets/d/.../edit"` (la cuenta de
  servicio necesita acceso de lectura). La app te muestra qué pestañas ve, para que
  puedas confirmar.
* Los gastos entran **repartidos en partes iguales** entre las personas del hogar,
  que es la regla que usaba la v1 ("mitad y mitad" al cerrar el mes).
* Los links de comprobantes de la v1 se conservan tal cual (se ven, no se descargan).
* Las compras pendientes se anotan en la lista del hogar.
* Las filas con fecha inválida o sin detalle se omiten y el resumen dice cuántas.
* Queda registrado en *Actividad* cuándo se importó. Si volvés a importar, la app te
  avisa que se van a duplicar.
* Se puede revertir: los gastos importados se pueden anular uno por uno, o eliminar
  el hogar y volver a empezar.

## Opción B: por línea de comandos

Útil si preferís no entrar a la app, o si querés importar un CSV exportado a mano.

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
