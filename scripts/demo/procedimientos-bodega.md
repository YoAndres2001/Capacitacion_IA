# Procedimientos Operativos de Bodega — WMS

## 1. Estructura física de la bodega

La bodega se organiza en una jerarquía de cuatro niveles que el sistema respeta en todos
sus movimientos:

1. **Bodega**: unidad física completa. Cada bodega tiene un código único de tres letras.
2. **Zona**: agrupación lógica dentro de la bodega (recepción, almacenaje, picking, despacho).
3. **Pasillo**: subdivisión de la zona, identificado con número correlativo.
4. **Ubicación**: posición exacta donde se deposita la mercadería. Su código combina
   pasillo, rack, nivel y posición, con el formato `P01-R03-N02-P05`.

Cada ubicación tiene una **capacidad máxima** expresada en unidades o en pallets. El sistema
impide depositar mercadería que exceda esa capacidad y sugiere ubicaciones alternativas de
la misma zona.

Las ubicaciones se clasifican además por **tipo de almacenamiento**: piso, rack selectivo,
rack drive-in, estantería liviana y cámara de frío. La cámara de frío exige que el producto
tenga habilitada la marca "requiere refrigeración" en su ficha maestra.

## 2. Recepción de mercadería

### 2.1 Recepción contra orden de compra

El procedimiento estándar tiene seis pasos:

1. El transportista entrega la guía de despacho del proveedor en portería.
2. El operador busca la **orden de compra** en el sistema por número o por proveedor.
3. El sistema muestra las líneas pendientes de recepción con su cantidad esperada.
4. El operador cuenta físicamente y digita la cantidad recibida por cada SKU.
5. Si hay diferencia, el sistema exige seleccionar un **motivo de diferencia** de la lista:
   faltante de proveedor, sobrante, producto dañado, producto vencido o error de guía.
6. El operador confirma. El sistema genera el movimiento de entrada, actualiza el stock y
   crea la tarea de guardado (put-away).

Las diferencias superiores al 5 % del total de la línea quedan **retenidas** y requieren
aprobación del jefe de bodega antes de afectar el stock.

### 2.2 Recepción sin orden de compra

Se usa para devoluciones de clientes y traspasos entre bodegas. Requiere indicar el motivo
y el centro de costo. Este tipo de recepción siempre queda marcado para auditoría.

### 2.3 Control de calidad

Los productos con la marca "requiere inspección" no ingresan directamente al stock
disponible: quedan en estado **cuarentena** hasta que un inspector registre el resultado.
Un resultado aprobado libera el stock; uno rechazado genera una devolución al proveedor.

## 3. Guardado (put-away)

Tras la recepción, el sistema genera automáticamente tareas de guardado. El algoritmo de
sugerencia de ubicación evalúa, en este orden:

1. Ubicaciones que ya contienen el mismo SKU y tienen espacio.
2. Ubicaciones vacías de la zona correspondiente a la rotación del producto.
3. Ubicaciones vacías de zonas alternativas compatibles.

Los productos de **alta rotación** se ubican cerca de la zona de picking para reducir el
recorrido del operador. La rotación se recalcula mensualmente según las salidas de los
últimos 90 días.

El operador puede rechazar la sugerencia e indicar otra ubicación, pero debe justificarlo.
El sistema registra estas desviaciones para el análisis de eficiencia.

## 4. Picking y preparación de pedidos

### 4.1 Estrategias de picking

El sistema soporta tres estrategias, configurables por tipo de pedido:

- **Picking discreto**: un operador prepara un pedido completo. Simple, pero implica más
  recorrido por unidad.
- **Picking por lote**: un operador recoge el mismo SKU para varios pedidos a la vez.
  Reduce recorrido, exige clasificación posterior.
- **Picking por zona**: cada operador cubre una zona; el pedido se consolida al final.
  Es la estrategia más eficiente en bodegas grandes.

### 4.2 Asignación de stock

La asignación sigue la regla **FEFO** (primero en vencer, primero en salir) para productos
con fecha de vencimiento, y **FIFO** (primero en entrar, primero en salir) para el resto.
El operador no puede tomar un lote distinto al asignado sin autorización.

### 4.3 Verificación

Antes del despacho, un segundo operador realiza la **verificación ciega**: cuenta lo
preparado sin ver la cantidad esperada. Si el conteo no coincide, el pedido vuelve a
preparación. Este control detecta la mayoría de los errores de picking.

## 5. Despacho

El despacho requiere que el pedido esté verificado y que exista un transporte asignado.
Los pasos son:

1. Consolidar los bultos y registrar su peso y volumen.
2. Generar la **guía de despacho electrónica**, que el sistema envía al SII.
3. Imprimir la etiqueta de bulto con su código de barras.
4. Registrar la salida del vehículo con hora y patente.

Una guía de despacho emitida no puede modificarse: si hay un error, debe anularse y emitirse
una nueva. La anulación requiere el rol de supervisor y queda registrada en la auditoría.

## 6. Inventario cíclico

El inventario cíclico cuenta una porción del inventario cada día en lugar de detener la
operación una vez al año. La clasificación ABC determina la frecuencia:

| Clase | Participación en el valor | Frecuencia de conteo |
|-------|---------------------------|----------------------|
| A | 80 % del valor, 20 % de los SKU | Mensual |
| B | 15 % del valor, 30 % de los SKU | Trimestral |
| C | 5 % del valor, 50 % de los SKU | Semestral |

Durante el conteo, las ubicaciones involucradas quedan **bloqueadas**: no admiten
movimientos hasta que el conteo se confirme. Las diferencias generan ajustes automáticos
que requieren motivo y centro de costo.

## 7. Indicadores de gestión

Los indicadores que la bodega revisa semanalmente son:

- **Exactitud de inventario**: porcentaje de ubicaciones sin diferencia en el conteo
  cíclico. La meta es 98 %.
- **Fill rate**: porcentaje de líneas de pedido despachadas completas a la primera. Meta 95 %.
- **Tiempo de ciclo de pedido**: horas entre la liberación del pedido y la salida del
  vehículo. Meta menor a 8 horas.
- **Productividad de picking**: líneas preparadas por operador por hora. Meta 60 líneas.
- **Ocupación de bodega**: porcentaje de ubicaciones ocupadas. Sobre 90 % la operación se
  vuelve ineficiente por falta de espacio de maniobra.

## 8. Seguridad y buenas prácticas

- Las grúas horquilla solo pueden ser operadas por personal con licencia clase D vigente.
- La velocidad máxima dentro de la bodega es de 10 km/h.
- Los pasillos deben permanecer despejados; está prohibido dejar pallets fuera de ubicación.
- Los productos peligrosos se almacenan en la zona segregada, separados por incompatibilidad
  química según la NCh 382.
- Todo incidente, incluso sin lesión, debe registrarse en el sistema dentro de las 24 horas.
