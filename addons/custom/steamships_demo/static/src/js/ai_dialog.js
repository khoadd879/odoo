/** @odoo-module **/
/* Steamships AI popup dialog (Phase A).
   REVERTED to pre-History state for debugging hang.
*/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

const STORAGE_KEY = "ssc_mode";

export class SteamshipsAIDialog extends Component {
    static components = { Dialog };
    static props = ["*"];
    static template = "steamships_demo.AIDialog";

    setup() {
        this.logRef = useRef("log");

        let initialMode = "staff";
        try {
            const m = localStorage.getItem(STORAGE_KEY);
            if (m === "client") initialMode = "client";
        } catch (_) { /* ignore */ }

        this.state = useState({
            mode: initialMode,
            groqEnabled: true,
            busy: false,
            draft: "",
            messages: [
                {
                    id: 1,
                    role: "assistant",
                    content: initialMode === "staff"
                        ? "Hello! I am the Steamships knowledge assistant (STAFF mode). Ask about services, prices, KYC, or approval rules."
                        : "Hello! I am the Steamships onboarding helper (CLIENT mode). I can answer questions about documents needed, registration steps, and what to expect. (Internal prices and SOPs are hidden in this mode.)",
                    sources: [],
                },
            ],
            _nextId: 2,
        });

        onMounted(() => this._scrollToBottom());
    }

    _scrollToBottom() {
        const el = this.logRef.el;
        if (el) el.scrollTop = el.scrollHeight;
    }

    _persistMode() {
        try { localStorage.setItem(STORAGE_KEY, this.state.mode); } catch (_) { /* ignore */ }
    }

    _pushBot(text, sources) {
        this.state.messages.push({
            id: this.state._nextId++,
            role: "assistant",
            content: text,
            sources: sources || [],
        });
        this._scrollToBottom();
    }

    switchStaff() {
        if (this.state.mode === "staff") return;
        this.state.mode = "staff";
        this._persistMode();
        this._pushBot("(switched to STAFF mode — full SOPs + prices)");
    }

    switchClient() {
        if (this.state.mode === "client") return;
        this.state.mode = "client";
        this._persistMode();
        this._pushBot("(switched to CLIENT mode — onboarding help only, no prices or internal SOPs)");
    }

    onKey(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    async send() {
        const text = (this.state.draft || "").trim();
        if (!text || this.state.busy) return;

        this.state.messages.push({
            id: this.state._nextId++,
            role: "user",
            content: text,
            sources: [],
        });
        this.state.draft = "";
        this.state.busy = true;
        this._scrollToBottom();

        try {
            const res = await fetch("/steamships/chat/api", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    params: {message: text, mode: this.state.mode},
                }),
            });
            const json = await res.json();
            if (json.error) {
                throw new Error(json.error.data && json.error.data.message || json.error.message);
            }
            const result = json.result || {};
            if (result.groq_enabled === false) this.state.groqEnabled = false;
            this._pushBot(result.reply || "(no reply)", result.sources || []);
        } catch (e) {
            this._pushBot("Error: " + (e && e.message ? e.message : e));
        } finally {
            this.state.busy = false;
            this._scrollToBottom();
        }
    }
}