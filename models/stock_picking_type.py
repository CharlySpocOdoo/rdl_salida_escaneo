# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    rdl_exigir_escaneo = fields.Boolean(
        string="Exigir revisión por escaneo antes de validar",
        default=False,
        help="Si está encendido, las salidas de este tipo que vienen de una orden de venta no se pueden validar "
             "hasta que lo contado en la pestaña «Revisión por escaneo» sea igual a lo que dice la salida. "
             "Los usuarios del grupo «Valida sin escaneo (handheld)» validan como siempre.",
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get("rdl_exigir_escaneo"):
            # Al encenderlo, las salidas abiertas con orden de venta muestran su tabla desde que se abren.
            # Si algo falla, el interruptor se guarda igual y las filas salen al escanear (mismo savepoint que stock.move).
            salidas = self.env["stock.picking"].search([
                ("picking_type_id", "in", self.ids),
                ("state", "not in", ("done", "cancel")),
                ("sale_id", "!=", False),
            ])
            self.env["stock.move"]._rdl_sincronizar_sin_frenar(salidas)
        return res
