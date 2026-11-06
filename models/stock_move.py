# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Solo estos cambios de un movimiento cambian la lista de productos de su salida. Nunca quantity, picked ni
# move_line_ids (lo que escriben las handhelds al surtir). picking_id va porque Odoo asigna los movimientos a la
# salida con un write de picking_id: sin él, la tabla de una salida nueva quedaría vacía hasta el primer escaneo.
CAMBIAN_LA_LISTA = frozenset({"picking_id", "product_id", "product_uom_qty", "product_uom", "state"})


class StockMove(models.Model):
    _inherit = "stock.move"

    def _rdl_salidas_a_revisar(self):
        """Filtro barato, antes de todo: solo salidas cuyo tipo tiene el interruptor, con orden de venta y abiertas."""
        return self.mapped("picking_id").filtered(
            lambda p: p.picking_type_id.rdl_exigir_escaneo and p.sale_id and p.state not in ("done", "cancel")
        )

    def _rdl_sincronizar_sin_frenar(self, salidas):
        """Crea o quita las filas de la tabla. Si algo falla, se deshace SOLO esto (savepoint) y el movimiento se
        guarda igual: la tabla se completa después, al escanear en la salida. Los errores del propio movimiento no
        pasan por aquí: ocurren antes, en super()."""
        if not salidas:
            return
        try:
            with self.env.cr.savepoint():
                salidas._rdl_sincronizar_lineas_guardadas()
        except Exception:  # noqa: BLE001 — nunca frenar el inventario por la tabla de revisión
            _logger.warning("rdl_salida_escaneo: no se pudieron preparar las filas de las salidas %s; se completan "
                            "al escanear.", salidas.ids, exc_info=True)

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._rdl_sincronizar_sin_frenar(moves._rdl_salidas_a_revisar())
        return moves

    def write(self, vals):
        if not CAMBIAN_LA_LISTA & set(vals):
            return super().write(vals)
        antes = self._rdl_salidas_a_revisar() if "picking_id" in vals else self.env["stock.picking"]
        res = super().write(vals)
        self._rdl_sincronizar_sin_frenar(antes | self._rdl_salidas_a_revisar())
        return res
