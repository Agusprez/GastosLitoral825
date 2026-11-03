# Términos y privacidad (borrador para revisar)

> **Aviso:** esto es un borrador de trabajo para que el servicio tenga textos
> razonables desde el día uno. **No es asesoramiento legal.** Antes de cobrar, hacé
> revisar estos textos por alguien con formación jurídica en tu jurisdicción
> (Argentina), sobre todo la parte de datos personales (Ley 25.326).

## Términos del servicio

1. **Qué es el servicio.** Cuentas Claras es una herramienta para registrar gastos
   compartidos de un hogar y calcular saldos entre sus integrantes. No es un banco,
   una billetera virtual ni un medio de pago: no mueve dinero ni garantiza pagos
   entre personas.
2. **Cuenta.** Para usar el servicio hay que crear una cuenta con un email válido y
   una contraseña. La persona usuaria es responsable de mantener la confidencialidad
   de su contraseña y de la actividad de su cuenta.
3. **Hogares e invitaciones.** Quien crea un hogar lo administra y decide a quién
   invita. Los códigos de invitación son de uso personal: no se deben publicar.
4. **Uso aceptable.** No se permite usar el servicio para actividades ilícitas, para
   subir contenido de terceros sin autorización, ni para intentar acceder a datos de
   otros hogares.
5. **Planes y pagos.** El plan Gratis no tiene costo y tiene límites de uso. El plan
   Pro se cobra por adelantado, por hogar, según el precio publicado al momento de
   la contratación. Los pagos se coordinan por los medios que se indiquen; no hay
   cobros automáticos en esta versión.
6. **Cancelación.** Se puede dejar de usar el servicio en cualquier momento. Al
   eliminar una cuenta se borran sus datos personales y los gastos que cargó. Los
   datos del hogar compartido pueden subsistir para no descuadrar los saldos de las
   demás personas.
7. **Disponibilidad.** El servicio se ofrece "tal como está". Se hace lo razonable
   para que esté disponible, pero no se garantiza ausencia de interrupciones ni
   recuperación total ante un incidente. Para datos críticos, exportá tu respaldo
   (CSV/JSON) periódicamente.
8. **Límite de responsabilidad.** No se responde por decisiones tomadas a partir de
   los números mostrados ni por diferencias derivadas de datos mal cargados. La
   herramienta calcula sobre lo que cada persona carga.
9. **Cambios.** Estos términos pueden actualizarse; los cambios relevantes se
   avisarán dentro de la app antes de aplicarse.

## Política de privacidad

**Qué datos se guardan**

* De la cuenta: nombre, email, hash de la contraseña (no la contraseña), fechas de
  alta e ingreso.
* Del hogar: nombre del hogar, integrantes, gastos (fecha, detalle, monto,
  categoría, quién pagó, entre quiénes se divide), compras y pagos registrados.
* Comprobantes: la imagen que se sube, guardada de forma privada.
* Técnicos: sesiones (token hasheado y vencimiento) y registro de actividad del
  hogar (quién hizo qué y cuándo).

**Cómo se protegen**

* Contraseñas con `scrypt` (hash con sal, irreversible).
* Datos cifrados en reposo con ChaCha20 + HMAC-SHA256. La clave no se guarda en la
  planilla.
* Comprobantes accesibles sólo para integrantes del hogar.
* Acceso a la base (planilla/archivo) restringido al operador del servicio.

**Para qué se usan**

* Prestar el servicio (calcular saldos, mostrar el historial, enviar invitaciones).
* Soporte cuando la persona lo pide.
* Métricas agregadas (cantidad de cuentas y hogares), sin datos personales.

**Con quién se comparten**

* No se venden ni se ceden datos personales a terceros.
* Se usan proveedores de infraestructura (Google Sheets/Drive y el hosting), que
  procesan los datos por cuenta del operador.
* Se pueden entregar datos si una autoridad competente lo exige legalmente.

**Cuánto tiempo**

* Mientras la cuenta esté activa.
* Al eliminarla: se borran los datos personales; el registro contable del hogar
  puede mantenerse sin datos identificatorios por hasta 12 meses, para no alterar
  saldos de otras personas.

**Derechos**

* Acceso, rectificación y supresión: desde *Mi cuenta* se pueden editar los datos,
  exportar todo (CSV/JSON) y eliminar la cuenta.
* Para cualquier pedido: `soporte_email` (ver configuración).

**Menores**

El servicio no está dirigido a menores de 16 años.

**Cookies**

Se usa una única cookie (`cc_sesion`) para mantener la sesión iniciada. No hay
cookies de publicidad ni rastreadores de terceros.
