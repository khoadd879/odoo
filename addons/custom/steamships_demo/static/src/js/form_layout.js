/** @odoo-module **/
/* Steamships: force form sheet + chatter layout to fixed widths.
 * Injects CSS rules at runtime to bypass Odoo core's flex: 2 1 990px collapse.
 */

(function () {
    if (document.getElementById('steamships-form-layout-css')) {
        return; // Already injected
    }
    const css = `
        .o_form_view.o_xxl_form_view .o_form_sheet_bg {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            max-width: calc(100% - 380px) !important;
            width: auto !important;
        }
        .o_form_view .oe_chatter.oe_chatter_aside {
            flex: 0 0 380px !important;
            max-width: 380px !important;
            width: 380px !important;
        }
        .o_form_view .o_form_renderer {
            align-items: stretch !important;
        }
    `;
    const style = document.createElement('style');
    style.id = 'steamships-form-layout-css';
    style.type = 'text/css';
    style.textContent = css;
    document.head.appendChild(style);
})();