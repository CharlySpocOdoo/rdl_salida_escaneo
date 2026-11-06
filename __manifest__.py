# -*- coding: utf-8 -*-
{
    "name": "Revisión por escaneo de salidas (Logística)",
    "version": "18.0.1.0.1",
    "summary": "Escanea cada pieza de la salida LOGIS/OUT y no deja validar si falta o sobra algo.",
    "description": """
Revisión por escaneo de salidas
===============================
En los tipos de operación con el interruptor «Exigir revisión por escaneo» encendido, las salidas que vienen de una
orden de venta muestran la pestaña «Revisión por escaneo». Cada escaneo suma 1; también se puede escribir el SKU
(se compara en mayúsculas de los dos lados) o escribir la cantidad final de un producto. «Validar» no deja terminar si
falta o sobra una pieza. Los usuarios del grupo «Valida sin escaneo (handheld)» validan como siempre.
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
    "installable": True,
    "application": False,
}
