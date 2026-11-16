# -*- coding: utf-8 -*-
{
    "name": "Revisión por escaneo de salidas (Logística)",
    "version": "18.0.1.0.4",
    "summary": "Escanea cada pieza de la salida LOGIS/OUT y no deja validar si falta o sobra algo.",
    "description": """
Revisión por escaneo de salidas
===============================
En los tipos de operación con el interruptor «Exigir revisión por escaneo» encendido, las salidas que vienen de una
orden de venta muestran la pestaña «Revisión por escaneo». Cada escaneo suma 1; también se puede escribir el SKU
(se compara en mayúsculas de los dos lados) o escribir la cantidad final de un producto. «Validar» no deja terminar si
falta o sobra una pieza. Los usuarios del grupo «Valida sin escaneo (handheld)» validan como siempre.
Desde la 18.0.1.0.2, la tabla lleva a la línea del último producto escaneado y la pinta, el cursor regresa a
«Escribir SKU», y cada línea muestra precio unitario, descuento e importe, de la orden de venta, con el total.
Desde la 18.0.1.0.3 el conteo es a ciegas: la pantalla no muestra lo que dice la salida ni si ya cuadra, el cursor queda
en «Contado» de la línea escaneada y el lector cuenta aunque el cursor esté en «Contado».
Desde la 18.0.1.0.4, el precio, el importe y el «Total» van con el IVA incluido, como la orden de venta.
""",
    "author": "Rosa de Lima Cosméticos",
    "license": "LGPL-3",
    "category": "Inventory/Inventory",
    "depends": ["stock", "sale_stock", "barcodes"],
    "data": [
        "security/rdl_salida_escaneo_security.xml",
        "security/ir.model.access.csv",
        "views/stock_picking_type_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "rdl_salida_escaneo/static/src/rdl_escaneo_lista.js",
            "rdl_salida_escaneo/static/src/rdl_escaneo_lista.scss",
        ],
    },
    "installable": True,
    "application": False,
}
