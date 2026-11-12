# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


def cantidad_texto(qty):
    """12.0 → «12»; 2.5 → «2.5». Para los mensajes."""
    return ("%.2f" % qty).rstrip("0").rstrip(".") if qty is not None else "0"


class RdlSalidaEscaneoLinea(models.Model):
    _name = "rdl.salida.escaneo.linea"
    _description = "Revisión por escaneo: lo contado de un producto en una salida"
    _order = "picking_id, id"

    picking_id = fields.Many2one("stock.picking", string="Salida", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="picking_id.company_id", store=True, index=True)
    product_id = fields.Many2one("product.product", string="Producto", required=True, ondelete="restrict")
    rdl_codigo_sku = fields.Char(related="product_id.default_code", string="SKU")
    product_uom_id = fields.Many2one(related="product_id.uom_id", string="Unidad")
    rdl_contado = fields.Float(
        string="Contado", digits="Product Unit of Measure", default=0.0,
        help="Cada escaneo suma 1. Si escribes un número aquí, ese es el total final de este producto.",
    )
    rdl_esperado = fields.Float(string="Dice la salida", digits="Product Unit of Measure", compute="_compute_rdl_diferencia")
    rdl_diferencia = fields.Float(string="Diferencia (contado − salida)", digits="Product Unit of Measure",
                                  compute="_compute_rdl_diferencia")
    rdl_estado = fields.Selection(
        [("falta", "Falta"), ("completo", "Completo"), ("sobra", "Sobra")],
        string="Estado", compute="_compute_rdl_diferencia",
    )
    rdl_diferencia_texto = fields.Char(string="Diferencia", compute="_compute_rdl_diferencia")

    # 1.0.2 · Función 1: la línea del último producto escaneado o escrito. La marca _rdl_contar y la pinta la lista.
    # Sin guardar: solo vive en la pantalla.
    rdl_ultimo = fields.Boolean(string="Último escaneado", store=False)

    # 1.0.2 · Función 2: precio, descuento e importe, de los renglones de la orden de venta que generó la salida.
    # Computados y sin guardar: se calculan al abrir la salida y al contar. Sin IVA.
    rdl_moneda_id = fields.Many2one("res.currency", string="Moneda", related="picking_id.rdl_moneda_id")
    rdl_precio_unitario = fields.Float(
        string="Precio unitario", digits="Product Price", compute="_compute_rdl_importe",
        help="Sin IVA, por unidad del producto. Sale de la orden de venta; si el producto viene en varios renglones, "
             "es el promedio ponderado por cantidad.",
    )
    rdl_descuento = fields.Float(
        string="% Descuento", digits="Discount", compute="_compute_rdl_importe",
        help="El descuento del renglón de la orden de venta; si son varios, el promedio ponderado por cantidad.",
    )
    rdl_importe = fields.Monetary(
        string="Importe", currency_field="rdl_moneda_id", compute="_compute_rdl_importe",
        help="Contado × precio unitario × (1 − descuento / 100). Sin IVA.",
    )

    _sql_constraints = [
        ("rdl_unico_por_salida", "unique(picking_id, product_id)",
         "Este producto ya tiene su fila en la revisión por escaneo de esta salida."),
    ]

    @api.depends("rdl_contado", "product_id", "picking_id.move_ids.product_uom_qty", "picking_id.move_ids.state",
                 "picking_id.move_ids.product_uom", "picking_id.move_ids.product_id")
    def _compute_rdl_diferencia(self):
        # 1.0.2: lo que dice la salida se calcula una vez por salida, no una vez por línea (salidas de cientos de
        # productos).
        por_salida = {}
        for linea in self:
            esperado = 0.0
            if linea.product_id and len(linea.picking_id) == 1:
                if linea.picking_id not in por_salida:
                    por_salida[linea.picking_id] = linea.picking_id._rdl_esperado()
                esperado = por_salida[linea.picking_id].get(linea.product_id, 0.0)
            linea.rdl_esperado = esperado
            linea.rdl_diferencia = linea.rdl_contado - esperado
            rounding = linea.product_id.uom_id.rounding or 0.01
            cmp = float_compare(linea.rdl_contado, esperado, precision_rounding=rounding)
            if cmp < 0:
                linea.rdl_estado = "falta"
                linea.rdl_diferencia_texto = _("Faltan %s", cantidad_texto(esperado - linea.rdl_contado))
            elif cmp > 0:
                linea.rdl_estado = "sobra"
                linea.rdl_diferencia_texto = _("Sobran %s", cantidad_texto(linea.rdl_contado - esperado))
            else:
                linea.rdl_estado = "completo"
                linea.rdl_diferencia_texto = "✔"

    @api.depends("rdl_contado", "product_id", "picking_id.move_ids.sale_line_id", "picking_id.move_ids.product_uom_qty",
                 "picking_id.move_ids.state", "picking_id.move_ids.product_uom", "picking_id.move_ids.product_id",
                 "picking_id.move_ids.sale_line_id.price_unit", "picking_id.move_ids.sale_line_id.discount",
                 "picking_id.move_ids.sale_line_id.product_uom")
    def _compute_rdl_importe(self):
        por_salida = {}
        for linea in self:
            precio = descuento = 0.0
            if linea.product_id and len(linea.picking_id) == 1:
                if linea.picking_id not in por_salida:
                    por_salida[linea.picking_id] = linea.picking_id._rdl_precios()
                precio, descuento = por_salida[linea.picking_id].get(linea.product_id, (0.0, 0.0))
            linea.rdl_precio_unitario = precio
            linea.rdl_descuento = descuento
            linea.rdl_importe = linea.rdl_contado * precio * (1.0 - descuento / 100.0)

    @api.constrains("rdl_contado")
    def _check_rdl_contado(self):
        for linea in self:
            if linea.rdl_contado < 0:
                raise ValidationError(_("El contado de %s no puede ser negativo.", linea.product_id.display_name))
