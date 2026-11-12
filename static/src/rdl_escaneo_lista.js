/** @odoo-module **/
/*
 * rdl_salida_escaneo 18.0.1.0.2 · Función 1: llevar a la línea del producto encontrado.
 *
 * Widget para la tabla de la «Revisión por escaneo» (rdl_linea_escaneo_ids). Es la tabla de siempre de Odoo, más dos
 * cosas:
 *  1. Cada vez que sube rdl_escaneos (un escaneo o un SKU con Enter), lleva la tabla a la línea marcada como última
 *     (rdl_ultimo), al centro de la pantalla, y regresa el cursor a «Escribir SKU» sin mover la pantalla. Así la
 *     despachadora sigue escaneando sin dar clic.
 *  2. Si escribe una cantidad a mano en «Contado» y da Enter, el cursor regresa a «Escribir SKU».
 * La línea se pinta con la decoración de la lista y el estilo de rdl_escaneo_lista.scss.
 * No escribe nada: solo mueve la pantalla y el cursor.
 */
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { onWillUnmount, onWillUpdateProps, reactive, useExternalListener } from "@odoo/owl";

const CLASE_LISTA = "o_rdl_escaneo_lista";
const CLASE_SKU = "o_rdl_escribir_sku";

export class RdlEscaneoX2ManyField extends X2ManyField {
    setup() {
        super.setup();
        this.rdlVivo = true;
        this.rdlObservar(this.props.record);
        // Si la pantalla pasa a otra salida (flechas de anterior/siguiente), se observa la nueva.
        onWillUpdateProps((siguientes) => {
            if (siguientes.record !== this.props.record) {
                this.rdlObservar(siguientes.record);
            }
        });

        // Enter en «Contado» (cantidad escrita a mano): el cursor regresa a «Escribir SKU». En fase de captura y sin
        // detener el evento: Odoo guarda la cantidad como siempre.
        useExternalListener(window, "keydown", (ev) => this.rdlEnterEnContado(ev), { capture: true });

        onWillUnmount(() => {
            this.rdlVivo = false;
        });
    }

    /**
     * Observa rdl_escaneos de la salida. La función reactive de OWL avisa cuando cambia una clave que se leyó por el
     * proxy; después de cada aviso se vuelve a leer para seguir escuchando. Cada salida tiene su propio observador.
     */
    rdlObservar(record) {
        const token = {};
        this.rdlToken = token;
        this.rdlEscaneosVistos = record.data.rdl_escaneos || 0;
        const salida = reactive(record, () => this.rdlAlCambiar(salida, token));
        this.rdlAlCambiar(salida, token);
    }

    rdlAlCambiar(salida, token) {
        const n = salida.data.rdl_escaneos || 0;   // leerlo es lo que mantiene la escucha
        if (!this.rdlVivo || token !== this.rdlToken) {
            return;                                 // pantalla cerrada, o es el observador de otra salida
        }
        if (n > this.rdlEscaneosVistos) {
            this.rdlEscaneosVistos = n;
            this.rdlIrALineaYRegresarCursor(10);
        } else if (n < this.rdlEscaneosVistos) {
            this.rdlEscaneosVistos = n;            // la salida se guardó o se volvió a cargar: no se mueve nada
        }
    }

    /** Espera a que la tabla ya muestre el cambio (unos cuadros de pantalla) y luego actúa. */
    rdlIrALineaYRegresarCursor(intentos) {
        requestAnimationFrame(() => {
            if (!this.rdlVivo) {
                return;
            }
            const ultima = this.list && this.list.records.find((r) => r.data.rdl_ultimo);
            const fila = ultima && document.querySelector(`.${CLASE_LISTA} .o_data_row[data-id="${ultima.id}"]`);
            if (ultima && !fila && intentos > 0) {
                this.rdlIrALineaYRegresarCursor(intentos - 1);
                return;
            }
            this.rdlRegresarCursor();
            if (fila) {
                fila.scrollIntoView({ block: "center", behavior: "smooth" });
            }
        });
    }

    /** El cursor a «Escribir SKU», sin mover la pantalla. No lo hace si hay una ventana encima (un diálogo). */
    rdlRegresarCursor() {
        const activo = document.activeElement;
        if (activo && activo.closest && activo.closest(".modal")) {
            return;
        }
        const casilla = document.querySelector(`.${CLASE_SKU} input`);
        if (casilla && casilla !== activo) {
            casilla.focus({ preventScroll: true });
        }
    }

    rdlEnterEnContado(ev) {
        if (ev.key !== "Enter" || !ev.target || !ev.target.closest) {
            return;
        }
        if (!ev.target.closest(`.${CLASE_LISTA} .o_data_row`)) {
            return;
        }
        // Después de que Odoo procese el Enter y guarde la cantidad.
        setTimeout(() => {
            if (this.rdlVivo) {
                this.rdlRegresarCursor();
            }
        }, 150);
    }
}

registry.category("fields").add("rdl_escaneo_one2many", {
    ...x2ManyField,
    component: RdlEscaneoX2ManyField,
});
