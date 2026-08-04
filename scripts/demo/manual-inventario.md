# Manual de Inventario — Módulo WMS

## 1. Conceptos generales

El **inventario** es el registro valorizado de todas las existencias que la empresa mantiene
en sus bodegas. En el sistema, cada existencia se identifica por la combinación de SKU,
bodega y ubicación.

Existen tres tipos de stock que el sistema maneja por separado:

- **Stock físico**: lo que efectivamente está en la bodega.
- **Stock comprometido**: unidades reservadas por pedidos de venta aún no despachados.
- **Stock disponible**: stock físico menos stock comprometido. Es el que se ofrece al vender.

## 2. Recepción de mercadería

El procedimiento de recepción tiene cuatro pasos obligatorios:

1. Ubicar la **orden de compra** (OC) en el módulo de Abastecimiento.
2. Registrar la **guía de despacho** del proveedor indicando el número y la fecha.
3. Contar físicamente y digitar las cantidades recibidas por SKU.
4. Confirmar la recepción. El sistema genera el movimiento de entrada y actualiza el stock.

Si la cantidad recibida difiere de la ordenada, el sistema exige indicar un **motivo de
diferencia**. Las diferencias sobre el 5 % requieren aprobación del jefe de bodega.

## 3. Inventario cíclico

El **inventario cíclico** consiste en contar una porción del inventario todos los días, en
lugar de detener la operación una vez al año para un inventario general. La clasificación
ABC define la frecuencia:

| Clase | Criterio | Frecuencia de conteo |
|-------|----------|----------------------|
| A | 20 % de los SKU que representan el 80 % del valor | Mensual |
| B | 30 % de los SKU, 15 % del valor | Trimestral |
| C | 50 % de los SKU, 5 % del valor | Semestral |

Para ejecutar un conteo cíclico:

1. Generar la **hoja de conteo** desde Inventario → Conteos → Nuevo conteo cíclico.
2. Seleccionar la clase (A, B o C) y la bodega.
3. Contar en terreno y digitar las cantidades en la hoja.
4. Revisar el **reporte de diferencias** antes de confirmar.
5. Confirmar. El sistema genera automáticamente los ajustes necesarios.

Una regla importante: durante un conteo cíclico las ubicaciones involucradas quedan
**bloqueadas** para movimientos, de modo que nadie pueda mover mercadería mientras se cuenta.

## 4. Ajustes y mermas

Un **ajuste de inventario** corrige una diferencia entre el stock del sistema y el stock real.
Todo ajuste requiere:

- Motivo (merma, rotura, vencimiento, error de digitación, robo).
- Centro de costo al que se imputa la pérdida.
- Autorización del jefe de bodega si el monto supera 50 UF.

Las **mermas** por vencimiento se registran con el motivo correspondiente y afectan el
resultado del período. El sistema no permite ajustar a stock negativo.

## 5. Reportes

Los reportes más usados del módulo son:

- **Stock valorizado**: existencias por bodega con su valor según costo promedio ponderado.
- **Kardex por SKU**: todos los movimientos de un producto en un rango de fechas.
- **Diferencias de inventario**: resultado de los conteos cíclicos del período.
- **Rotación de inventario**: cuántas veces se renovó el stock, útil para detectar productos
  de baja rotación.

El costo se calcula siempre con **costo promedio ponderado**, que se recalcula en cada
recepción con la fórmula: (valor stock anterior + valor de la compra) / (unidades anteriores +
unidades compradas).
