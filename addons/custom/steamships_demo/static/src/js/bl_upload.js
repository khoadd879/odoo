/** @odoo-module **/
/* Steamships B/L Scan Upload — opens file picker, posts to /steamships/bl/extract.
   For demo: doesn't strictly need server-side action (ext controller does it all),
   but kept as a class hook so the form's "Upload Scan" button is functional.
   The button currently calls action_upload_scan_wizard which is a no-op Python
   wrapper; the real flow is the form view's stat button + this JS.
*/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    async setup() {
        await super.setup(...arguments);
        // Listen for custom event dispatched from menu/button.
        this._ssc_blUploadHandler = (ev) => this._sscUploadBLScan(ev.detail.recordId);
        document.addEventListener('ssc:bl_upload', this._ssc_blUploadHandler);
    },

    _sscUploadBLScan(recordId) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*,application/pdf';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const fd = new FormData();
            fd.append('scan', file);
            fd.append('create', '1');
            // Include model + id in form so controller can attach
            fd.append('res_model', 'bill.of.lading');
            fd.append('res_id', String(recordId || ''));
            try {
                const res = await fetch('/steamships/bl/extract', {
                    method: 'POST',
                    body: fd,
                });
                const json = await res.json();
                if (json.error) {
                    alert('Upload failed: ' + json.error);
                    return;
                }
                // Force reload form to show new extracted fields
                window.location.reload();
            } catch (err) {
                alert('Upload error: ' + err.message);
            }
        };
        input.click();
    },

    destroy() {
        document.removeEventListener('ssc:bl_upload', this._ssc_blUploadHandler);
        super.destroy(...arguments);
    },
});
