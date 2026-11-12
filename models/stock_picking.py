# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

from .rdl_salida_escaneo_linea import cantidad_texto

GRUPO_SIN_ESCANEO = "rdl_salida_escaneo.group_valida_sin_escaneo"
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "barcodes.barcode_events_mixin"]

    rdl_linea_escaneo_ids = fields.One2many("rdl.salida.escaneo.linea", "picking_id", string="Revisión por escaneo")
    rdl_exige_escaneo = fields.Boolean(string="Exige revisión por escaneo", compute="_compute_rdl_exige_escaneo")
    rdl_estado_escaneo = fields.Selection(
        [("sin_empezar", "Sin empezar"), ("faltan", "Faltan piezas"), ("sobran", "Sobran piezas"), ("completa", "Completa")],
        string="Estado de la revisión", compute="_compute_rdl_estado_escaneo",
    )
    rdl_letrero_escaneo = fields.Char(string="Letrero de la revisión", compute="_compute_rdl_estado_escaneo")
    rdl_sku = fields.Char(
        string="Escribir SKU", store=False,
        help="Escribe el SKU y presiona Enter: suma 1, igual que un escaneo. Se compara en mayúsculas: encuentra el SKU aunque esté guardado con minúsculas.",
    )
    # 1.0.2 · Función 1: cuántos escaneos o SKU van en esta pantalla. Sube en cada intento; con eso la tabla sabe
    # que debe llevar a la línea marcada y regresar el cursor a «Escribir SKU». Sin guardar.
    rdl_escaneos = fields.Integer(string="Escaneos en pantalla", store=False)
    # 1.0.2 · Función 2: la moneda de la orden de venta y el total de la revisión, sin IVA. Computados, sin guardar.
    rdl_moneda_id = fields.Many2one("res.currency", string="Moneda de la venta", compute="_compute_rdl_moneda")
    rdl_total_escaneo = fields.Monetary(
        string="Total", currency_field="rdl_moneda_id", compute="_compute_rdl_total_escaneo",
        help="Suma de los importes de la revisión por escaneo. Sin IVA.",
    )

    # ── Cuándo aplica ────────────────────────────────────────────────────────

    @api.depends("picking_type_id.rdl_exigir_escaneo", "sale_id", "state")
    def _compute_rdl_exige_escaneo(self):
        for picking in self:
            picking.rdl_exige_escaneo = bool(
                picking.picking_type_id.rdl_exigir_escaneo
                and picking.sale_id
                and picking.state not in ("done", "cancel")
            )

    # ── Qué dice la salida y qué se ha contado ───────────────────────────────

    def _rdl_esperado(self):
        """Por producto: lo que dice la salida (sus movimientos no cancelados), en la unidad del producto."""
        self.ensure_one()
        esperado = defaultdict(float)
        for move in self.move_ids:
            if move.state == "cancel" or not move.product_id:
                continue
            unidad = move.product_uom or move.product_id.uom_id
            esperado[move.product_id] += unidad._compute_quantity(move.product_uom_qty, move.product_id.uom_id, round=False)
        return esperado

    def _rdl_diferencias(self):
        """(faltan, sobran, total contado). faltan y sobran son listas de (producto, cantidad)."""
        self.ensure_one()
        esperado = self._rdl_esperado()
        contado = defaultdict(float)
        for linea in self.rdl_linea_escaneo_ids:
            contado[linea.product_id] += linea.rdl_contado
        faltan, sobran = [], []
        for producto in sorted(set(esperado) | set(contado), key=lambda p: p.display_name or ""):
            e, c = esperado.get(producto, 0.0), contado.get(producto, 0.0)
            cmp = float_compare(c, e, precision_rounding=producto.uom_id.rounding or 0.01)
            if cmp < 0:
                faltan.append((producto, e - c))
            elif cmp > 0:
                sobran.append((producto, c - e))
        return faltan, sobran, sum(contado.values())

    @api.depends("rdl_linea_escaneo_ids.rdl_contado", "rdl_linea_escaneo_ids.product_id", "move_ids.product_uom_qty",
                 "move_ids.state", "move_ids.product_id", "move_ids.product_uom")
    def _compute_rdl_estado_escaneo(self):
        for picking in self:
            faltan, sobran, total = picking._rdl_diferencias()
            if float_is_zero(total, precision_digits=4):
                picking.rdl_estado_escaneo = "sin_empezar"
                picking.rdl_letrero_escaneo = _("Sin empezar: escanea la primera pieza o escribe el SKU.")
            elif sobran:
                picking.rdl_estado_escaneo = "sobran"
                picking.rdl_letrero_escaneo = _(
                    "Sobran %(piezas)s piezas de %(productos)s productos: corrige el contado antes de validar.",
                    piezas=cantidad_texto(sum(q for _p, q in sobran)), productos=len(sobran),
                )
            elif faltan:
                picking.rdl_estado_escaneo = "faltan"
                picking.rdl_letrero_escaneo = _(
                    "Faltan %(piezas)s piezas de %(productos)s productos.",
                    piezas=cantidad_texto(sum(q for _p, q in faltan)), productos=len(faltan),
                )
            else:
                picking.rdl_estado_escaneo = "completa"
                picking.rdl_letrero_escaneo = _("Completa: %s piezas revisadas. Ya puedes validar.", cantidad_texto(total))

    # ── 1.0.2 · Precio, descuento, importe y total (de la orden de venta) ────

    @api.depends("sale_id", "company_id")
    def _compute_rdl_moneda(self):
        for picking in self:
            # sudo solo para LEER la moneda de la venta: las despachadoras pueden no tener permiso de ventas.
            picking.rdl_moneda_id = picking.sudo().sale_id.currency_id or picking.company_id.currency_id

    @api.depends("rdl_linea_escaneo_ids.rdl_importe")
    def _compute_rdl_total_escaneo(self):
        for picking in self:
            picking.rdl_total_escaneo = sum(picking.rdl_linea_escaneo_ids.mapped("rdl_importe"))

    @staticmethod
    def _rdl_precio_sin_iva(linea_venta):
        """El precio unitario del renglón de venta, sin IVA. Si sus impuestos vienen incluidos en el precio, se quitan;
        si no, es price_unit tal cual. Solo para mostrar: si el cálculo de impuestos fallara, se usa price_unit y se
        anota un aviso en el registro del servidor, para que la pantalla de la salida nunca se caiga por esto."""
        # En Odoo 18 el campo es tax_id; la guarda es por si otra versión lo llama tax_ids.
        campo = "tax_id" if "tax_id" in linea_venta._fields else "tax_ids"
        impuestos = linea_venta[campo] if campo in linea_venta._fields else linea_venta.env["account.tax"]
        if not impuestos or "price_include" not in impuestos._fields or not any(impuestos.mapped("price_include")):
            return linea_venta.price_unit
        try:
            return impuestos.compute_all(
                linea_venta.price_unit, currency=linea_venta.currency_id, quantity=1.0,
                product=linea_venta.product_id, partner=linea_venta.order_id.partner_shipping_id,
            )["total_excluded"]
        except Exception:  # noqa: BLE001
            _logger.warning("rdl_salida_escaneo: no se pudo quitar el IVA incluido del renglón de venta %s; "
                            "se muestra price_unit.", linea_venta.id)
            return linea_venta.price_unit

    def _rdl_precios(self):
        """Por producto: (precio unitario sin IVA en la unidad del producto, % descuento), de los renglones de la orden
        de venta ligados a los movimientos de esta salida (move.sale_line_id). Si un producto viene de varios
        renglones, promedio ponderado por la cantidad de cada movimiento, para precio y descuento. Los renglones de
        venta se leen con sudo, SOLO para leer: aquí nunca se escribe en la venta."""
        self.ensure_one()
        acumulado = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0])   # peso, precio×peso, desc×peso, Σprecio, Σdesc, n
        for move in self.move_ids:
            if move.state == "cancel" or not move.product_id:
                continue
            linea_venta = move.sudo().sale_line_id
            if not linea_venta:
                continue
            producto = move.product_id
            unidad_movimiento = move.product_uom or producto.uom_id
            peso = unidad_movimiento._compute_quantity(move.product_uom_qty, producto.uom_id, round=False)
            unidad_venta = linea_venta.product_uom or producto.uom_id
            precio = unidad_venta._compute_price(self._rdl_precio_sin_iva(linea_venta), producto.uom_id)
            a = acumulado[producto]
            a[0] += peso
            a[1] += precio * peso
            a[2] += linea_venta.discount * peso
            a[3] += precio
            a[4] += linea_venta.discount
            a[5] += 1
        precios = {}
        for producto, (peso, precio_peso, desc_peso, suma_precio, suma_desc, n) in acumulado.items():
            if peso > 0:
                precios[producto] = (precio_peso / peso, desc_peso / peso)
            else:                                   # cantidades en 0: promedio simple
                precios[producto] = (suma_precio / n, suma_desc / n)
        return precios

    # ── Escanear y escribir el SKU ───────────────────────────────────────────

    def _rdl_productos_por_codigo(self, codigo):
        """Productos con ese código de barras: el propio del producto y los códigos extra de BrowseInfo (todos)."""
        Product = self.env["product.product"]
        codigo = (codigo or "").strip()
        if not codigo:
            return Product
        productos = Product.search([("barcode", "=", codigo)])
        if "product.barcode" in self.env:      # bi_multi_barcode_for_product, si está instalado
            Extra = self.env["product.barcode"].sudo()
            dominio = [("barcode", "=", codigo)]
            if "company_id" in Extra._fields:
                dominio.append(("company_id", "in", [False, self.company_id.id]))
            extra_ids = Extra.search(dominio).mapped("product_id").ids
            if extra_ids:
                productos |= Product.search([("id", "in", extra_ids)])
        return productos

    def _rdl_productos_por_sku(self, sku):
        """El SKU se compara en mayúsculas de los dos lados (Charly, 2026-11-06: «si, realiza el cambio»), así se
        encuentran también los guardados con minúsculas. Odoo busca con «ilike», que trae de más (_ y % son
        comodines y no distingue mayúsculas), y luego se filtra en Python con igualdad exacta en mayúsculas y sin
        espacios en las orillas. Si quedan dos o más productos, es repetido: el que llama avisa y no cuenta."""
        Product = self.env["product.product"]
        sku = (sku or "").strip().upper()
        if not sku:
            return Product
        candidatos = Product.search([("default_code", "ilike", sku)])
        return candidatos.filtered(lambda p: (p.default_code or "").strip().upper() == sku)

    def _rdl_sincronizar_lineas_guardadas(self):
        """Fuera de la pantalla (al crear o cambiar movimientos, o al encender el interruptor): deja una fila por
        producto de la salida, para que la tabla se vea completa desde que se abre. Quita las filas en 0 de productos
        que ya no están. El sudo es SOLO para las filas (rdl.salida.escaneo.linea): la salida y sus movimientos se leen
        con el usuario de siempre. Así quien mueve inventario sin permiso sobre estas filas (por ejemplo, las
        handhelds) no se frena."""
        Linea = self.env["rdl.salida.escaneo.linea"].sudo()
        for picking in self.filtered("rdl_exige_escaneo"):
            esperado = picking._rdl_esperado()
            filas = Linea.search([("picking_id", "=", picking.id)])
            existentes = set(filas.mapped("product_id").ids)
            nuevos = [{"picking_id": picking.id, "product_id": p.id, "rdl_contado": 0.0}
                      for p in esperado if p.id not in existentes]
            if nuevos:
                Linea.create(nuevos)
            ids_esperados = {p.id for p in esperado}
            sobrantes = filas.filtered(
                lambda l: l.product_id.id not in ids_esperados and float_is_zero(l.rdl_contado, precision_digits=4)
            )
            if sobrantes:
                sobrantes.unlink()

    def _rdl_sincronizar_lineas(self):
        """En pantalla (al escanear o escribir el SKU): una fila por cada producto de la salida, por si falta alguna."""
        existentes = set(self.rdl_linea_escaneo_ids.mapped("product_id").ids)
        nuevos = [p for p in self._rdl_esperado() if p.id not in existentes]
        if nuevos:
            self.rdl_linea_escaneo_ids = [Command.create({"product_id": p.id, "rdl_contado": 0.0}) for p in nuevos]

    @staticmethod
    def _rdl_aviso(titulo, mensaje):
        return {"warning": {"title": titulo, "message": mensaje, "type": "notification"}}

    def _rdl_contar(self, productos, que, es_codigo):
        """Suma 1 al producto encontrado y regresa el aviso para la pantalla. 1.0.2: marca su línea como la última
        escaneada (y desmarca la anterior) y sube rdl_escaneos en cada intento, para que la tabla lleve a esa línea y
        el cursor regrese a «Escribir SKU»."""
        self.ensure_one()
        self.rdl_escaneos = (self.rdl_escaneos or 0) + 1
        if not productos:
            mensaje = _("%s no es de ningún producto. No se contó.", que)
            if es_codigo:
                mensaje += " " + _("Escribe el SKU.")
            return self._rdl_aviso(_("No encontrado"), mensaje)
        if len(productos) > 1:
            return self._rdl_aviso(_("Repetido"), _(
                "%(que)s lo tienen %(n)s productos (%(nombres)s). No se contó: corrígelo en Odoo.",
                que=que, n=len(productos), nombres=", ".join(productos.mapped("display_name")),
            ))
        producto = productos
        esperado = self._rdl_esperado()
        if producto not in esperado:
            return self._rdl_aviso(_("No está en esta salida"),
                                   _("%s no está en esta salida. No se contó.", producto.display_name))
        self._rdl_sincronizar_lineas()
        linea = self.rdl_linea_escaneo_ids.filtered(lambda l: l.product_id == producto)[:1]
        linea.rdl_contado += 1
        for anterior in self.rdl_linea_escaneo_ids.filtered(lambda l: l.rdl_ultimo and l != linea):
            anterior.rdl_ultimo = False
        linea.rdl_ultimo = True
        e, c = esperado[producto], linea.rdl_contado
        cmp = float_compare(c, e, precision_rounding=producto.uom_id.rounding or 0.01)
        if cmp > 0:
            return self._rdl_aviso(_("Sobra"), _(
                "%(producto)s: ya van %(c)s y la salida dice %(e)s. Sobran %(s)s: corrige el contado.",
                producto=producto.display_name, c=cantidad_texto(c), e=cantidad_texto(e), s=cantidad_texto(c - e),
            ))
        if cmp == 0:
            return self._rdl_aviso(_("Completo"), _("%s completo ✔", producto.display_name))
        return self._rdl_aviso(_("Contado"), _("%(producto)s: %(c)s de %(e)s", producto=producto.display_name,
                                              c=cantidad_texto(c), e=cantidad_texto(e)))

    def on_barcode_scanned(self, barcode):
        if not self.rdl_exige_escaneo:
            return None
        codigo = (barcode or "").strip()
        return self._rdl_contar(self._rdl_productos_por_codigo(codigo), _("El código %s", codigo), es_codigo=True)

    @api.onchange("rdl_sku")
    def _onchange_rdl_sku(self):
        texto = self.rdl_sku
        if not texto:
            return None
        self.rdl_sku = False
        if not self.rdl_exige_escaneo:
            return None
        sku = texto.strip().upper()
        return self._rdl_contar(self._rdl_productos_por_sku(sku), _("El SKU %s", sku), es_codigo=False)

    # ── El bloqueo ───────────────────────────────────────────────────────────

    def _rdl_motivo_de_bloqueo(self):
        """El texto del error si esta salida no se puede validar; None si sí se puede."""
        self.ensure_one()
        if not self._rdl_esperado():
            return None          # salida sin productos: la revisa Odoo como siempre
        faltan, sobran, total = self._rdl_diferencias()
        partes = []
        if float_is_zero(total, precision_digits=4):
            partes.append(_("Todavía no se ha contado nada. Escanea las piezas en la pestaña «Revisión por escaneo»."))
        else:
            if faltan:
                partes.append(_("Faltan: %s.", ", ".join(f"{cantidad_texto(q)} {p.display_name}" for p, q in faltan)))
            if sobran:
                partes.append(_("Sobran: %s. Corrige el contado.",
                                ", ".join(f"{cantidad_texto(q)} {p.display_name}" for p, q in sobran)))
        sin_apartar = self.move_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
            and float_compare(m.quantity, m.product_uom_qty, precision_rounding=m.product_uom.rounding or 0.01) < 0
        )
        if sin_apartar:
            partes.append(_("La recolección no trajo todo (%s). Revisa el PICK antes de validar esta salida.",
                            ", ".join(sin_apartar.mapped("product_id.display_name"))))
        if not partes:
            return None
        return _("No se puede validar la salida %(salida)s:\n- %(detalle)s", salida=self.name, detalle="\n- ".join(partes))

    def button_validate(self):
        """Único punto de bloqueo. Por aquí pasan el botón «Validar», la validación de varias salidas desde la lista y
        el asistente de pendientes (que vuelve a llamar a este método). Quien tiene el grupo «Valida sin escaneo
        (handheld)» pasa directo, venga de la pantalla o de la API."""
        revisadas = {}
        if not self.env.user.has_group(GRUPO_SIN_ESCANEO):
            revisar = self.filtered("rdl_exige_escaneo")
            errores = [m for m in (p._rdl_motivo_de_bloqueo() for p in revisar) if m]
            if errores:
                raise UserError("\n\n".join(errores))
            for picking in revisar:
                revisadas[picking.id] = picking._rdl_diferencias()[2]
                picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel") and not m.picked).picked = True
        res = super().button_validate()
        for picking in self.browse(list(revisadas)).filtered(lambda p: p.state == "done"):
            picking.message_post(body=_("Revisión por escaneo completa: %s piezas.", cantidad_texto(revisadas[picking.id])))
        return res
