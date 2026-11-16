/** @odoo-module **/
/*
 * rdl_salida_escaneo 18.0.1.0.3 · La tabla de la «Revisión por escaneo» (rdl_linea_escaneo_ids).
 *
 * Es la tabla de siempre de Odoo, más esto:
 *  1. (1.0.2) Cada vez que sube rdl_escaneos (un escaneo o un SKU), lleva la tabla a la línea marcada como última
 *     (rdl_ultimo) y la deja al centro de la pantalla.
 *  2. (1.0.3, Charly 2026-11-15) El cursor queda DENTRO de «Contado» de esa línea, con el número seleccionado para
 *     teclear encima lo que contaron. El escaneo ya sumó 1 («La B»).
 *  3. (1.0.3) Si el cursor está en «Contado» y pasan el lector, el lector «teclea» el código en esa casilla. Aquí se
 *     detecta: muchas teclas muy seguidas que terminan en Enter. Entonces se quita lo tecleado, se deja el número que
 *     tenía y el código se manda a «Escribir SKU», que lo cuenta como cualquier escaneo. Lo que teclea una persona
 *     (despacio) es cantidad.
 *  4. (1.0.2) Enter de una persona en «Contado»: el cursor regresa a «Escribir SKU».
 * No escribe nada en Odoo por su cuenta: solo mueve la pantalla y el cursor, y pasa el código del lector a «Escribir
 * SKU», como si lo hubieran tecleado ahí.
 */
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { onWillUnmount, onWillUpdateProps, reactive, useExternalListener } from "@odoo/owl";

const CLASE_LISTA = "o_rdl_escaneo_lista";
const CLASE_SKU = "o_rdl_escribir_sku";
const CAMPO_CONTADO = "rdl_contado";

/*
 * UMBRAL DEL LECTOR (cómo se distingue al lector de una persona). Se prueba con el lector real; ver INSTALAR-v4.md.
 *  - LECTOR_MS_ENTRE_TECLAS: el máximo de milisegundos entre una tecla y la siguiente, y entre la última y el Enter,
 *    para que cuente como lector. Los lectores mandan cada tecla en menos de 20-30 ms; una persona rápida tarda 80 ms
 *    o más. Si el lector de la bodega es lento y sus códigos caen como cantidad, se sube (por ejemplo a 60).
 *  - LECTOR_MIN_CARACTERES: cuántas teclas como mínimo. Los códigos de barras tienen 8 o más; una cantidad, 1 a 4.
 */
export const LECTOR_MS_ENTRE_TECLAS = 40;
export const LECTOR_MIN_CARACTERES = 5;

export class RdlEscaneoX2ManyField extends X2ManyField {
    setup() {
        super.setup();
        this.rdlVivo = true;
        this.rdlRafaga = null;
        this.rdlObservar(this.props.record);
        // Si la pantalla pasa a otra salida (flechas de anterior/siguiente), se observa la nueva.
        onWillUpdateProps((siguientes) => {
            if (siguientes.record !== this.props.record) {
                this.rdlObservar(siguientes.record);
            }
        });
        // En fase de captura: aquí se ve cada tecla antes que Odoo. Solo se detiene el Enter del lector en «Contado».
        useExternalListener(window, "keydown", (ev) => this.rdlTecla(ev), { capture: true });
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
            this.rdlIrALinea(10);
        } else if (n < this.rdlEscaneosVistos) {
            this.rdlEscaneosVistos = n;            // la salida se guardó o se volvió a cargar: no se mueve nada
        }
    }

    rdlFila(id) {
        return document.querySelector(`.${CLASE_LISTA} .o_data_row[data-id="${id}"]`);
    }

    rdlHayDialogo() {
        const activo = document.activeElement;
        return Boolean(activo && activo.closest && activo.closest(".modal"));
    }

    /** Espera a que la tabla muestre el cambio y lleva a la línea marcada; luego, el cursor a su «Contado». */
    rdlIrALinea(intentos) {
        requestAnimationFrame(() => {
            if (!this.rdlVivo) {
                return;
            }
            const ultima = this.list && this.list.records.find((r) => r.data.rdl_ultimo);
            const fila = ultima && this.rdlFila(ultima.id);
            if (!fila) {
                if (ultima && intentos > 0) {
                    this.rdlIrALinea(intentos - 1);
                } else {
                    this.rdlCursorASku();          // sin línea marcada (no encontrado, repetido…): a «Escribir SKU»
                }
                return;
            }
            fila.scrollIntoView({ block: "center", behavior: "smooth" });
            if (!this.rdlHayDialogo()) {
                this.rdlEntrarAContado(ultima.id, 20, false);
            }
        });
    }

    /**
     * Pone el cursor dentro de «Contado» de la línea, con el número seleccionado. Si la línea no está en edición, da
     * un clic en su celda «Contado» (así entra Odoo a editar una línea) y espera a que aparezca la casilla.
     */
    rdlEntrarAContado(id, intentos, yaClic) {
        requestAnimationFrame(() => {
            if (!this.rdlVivo) {
                return;
            }
            const fila = this.rdlFila(id);
            const casilla = fila && fila.querySelector(`[name="${CAMPO_CONTADO}"] input`);
            if (casilla) {
                casilla.focus({ preventScroll: true });
                casilla.select();
                return;
            }
            if (fila && !yaClic) {
                const celda = fila.querySelector(`td[name="${CAMPO_CONTADO}"]`);
                if (celda) {
                    celda.click();
                    this.rdlEntrarAContado(id, intentos - 1, true);
                    return;
                }
            }
            if (intentos > 0) {
                this.rdlEntrarAContado(id, intentos - 1, yaClic);
            } else {
                this.rdlCursorASku();              // no se pudo entrar a «Contado»: al menos a «Escribir SKU»
            }
        });
    }

    /** El cursor a «Escribir SKU», sin mover la pantalla. No lo hace si hay una ventana encima (un diálogo). */
    rdlCursorASku() {
        if (this.rdlHayDialogo()) {
            return;
        }
        const casilla = document.querySelector(`.${CLASE_SKU} input`);
        if (casilla && casilla !== document.activeElement) {
            casilla.focus({ preventScroll: true });
        }
    }

    /** Cada tecla. Solo importa cuando el cursor está en la casilla «Contado» de esta tabla. */
    rdlTecla(ev) {
        const casilla = ev.target;
        const enContado = casilla && casilla.tagName === "INPUT" && casilla.closest
            && casilla.closest(`.${CLASE_LISTA} .o_data_row [name="${CAMPO_CONTADO}"]`);
        if (!enContado) {
            this.rdlRafaga = null;
            return;
        }
        const ahora = performance.now();
        if (ev.key === "Enter") {
            const r = this.rdlRafaga;
            this.rdlRafaga = null;
            const esLector = r && r.casilla === casilla && !r.repetida
                && r.texto.length >= LECTOR_MIN_CARACTERES
                && ahora - r.ultima <= LECTOR_MS_ENTRE_TECLAS;
            if (esLector) {
                // Es el lector: que Odoo no vea este Enter, se regresa el número de antes y el código va a contarse.
                ev.preventDefault();
                ev.stopPropagation();
                ev.stopImmediatePropagation();
                casilla.value = r.valorAntes;
                casilla.dispatchEvent(new Event("input", { bubbles: true }));
                this.rdlContarCodigo(r.texto);
                return;
            }
            // Enter de una persona: terminó de teclear la cantidad. Odoo la guarda y el cursor regresa a «Escribir SKU».
            setTimeout(() => {
                if (this.rdlVivo) {
                    this.rdlCursorASku();
                }
            }, 150);
            return;
        }
        if (ev.key.length !== 1 || ev.ctrlKey || ev.metaKey || ev.altKey) {
            return;                                 // flechas, borrar, Shift solo, atajos: no cuentan
        }
        const r = this.rdlRafaga;
        if (!r || r.casilla !== casilla || ahora - r.ultima > LECTOR_MS_ENTRE_TECLAS) {
            // Empieza una ráfaga nueva. Se guarda el número como estaba ANTES de esta tecla.
            this.rdlRafaga = { casilla, valorAntes: casilla.value, texto: ev.key, ultima: ahora, repetida: ev.repeat };
        } else {
            r.texto += ev.key;
            r.ultima = ahora;
            r.repetida = r.repetida || ev.repeat; // una tecla dejada apretada se repite rápido: no es el lector
        }
    }

    /** El código que tecleó el lector en «Contado» va a «Escribir SKU»: lo cuenta igual que cualquier escaneo. */
    rdlContarCodigo(codigo) {
        Promise.resolve(this.props.record.update({ rdl_sku: codigo })).catch(() => {
            this.rdlCursorASku();
        });
    }
}

registry.category("fields").add("rdl_escaneo_one2many", {
    ...x2ManyField,
    component: RdlEscaneoX2ManyField,
});
