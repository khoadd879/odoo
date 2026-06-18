/** @odoo-module **/
/* Steamships AI — AI chat button in systray. */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SteamshipsAIDialog } from "./ai_dialog";

export class SteamshipsAISystray extends Component {
    static props = [];
    static template = "steamships_demo.AISystray";

    setup() {
        this.dialog = useService("dialog");
    }

    onClick() {
        this.dialog.add(SteamshipsAIDialog, {
            title: "Steamships AI Assistant",
            size: "md",
        });
    }
}

registry.category("systray").add(
    "steamships.AISystray",
    { Component: SteamshipsAISystray },
    { sequence: 50 }
);