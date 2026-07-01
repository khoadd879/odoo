from odoo import http
import json

class TestController(http.Controller):
    @http.route('/steamships/test_settings_vals', type='http', auth='user', website=True, methods=['GET'])
    def t(self, **kwargs):
        from odoo.http import request
        env = request.env
        ICP = env["ir.config_parameter"]
        cid = ICP.get_param("steamships_google_calendar_client_id", default="") or ""
        cs = ICP.get_param("steamships_google_calendar_client_secret", default="") or ""
        ruri = ICP.get_param("steamships_google_calendar_redirect_uri", default="") or ""
        missing = []
        if not cid: missing.append("cid")
        if not cs: missing.append("cs")
        if not ruri: missing.append("ruri")
        return json.dumps({
            "cid_repr": repr(cid),
            "cs_repr": repr(cs),
            "ruri_repr": repr(ruri),
            "missing": missing,
            "configured": not missing,
        }, indent=2)
