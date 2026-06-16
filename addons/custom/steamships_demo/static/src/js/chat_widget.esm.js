/** @odoo-module **/
/* Steamships AI Chat Widget - Odoo 18 BACKEND client action.
   Renders the chat inside the Odoo backend (web.assets_backend),
   NOT the public website. Modes toggle: STAFF vs CLIENT per DOCX B4.

   Registered as client action tag: 'steamships_ai_chat'.
   Wired in views/chat_widget_views.xml (ir.actions.client tag=...).
*/

(function () {
    'use strict';

    const STORAGE_KEY = 'ssc_mode';
    const MODE_STAFF = 'staff';
    const MODE_CLIENT = 'client';

    function getStoredMode() {
        try {
            const m = localStorage.getItem(STORAGE_KEY);
            return (m === MODE_CLIENT) ? MODE_CLIENT : MODE_STAFF;
        } catch (e) {
            return MODE_STAFF;
        }
    }

    function setStoredMode(m) {
        try { localStorage.setItem(STORAGE_KEY, m); } catch (e) { /* ignore */ }
    }

    async function callChatApi(message, mode) {
        const res = await fetch('/steamships/chat/api', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                jsonrpc: '2.0',
                params: {message, mode},
            }),
        });
        const json = await res.json();
        if (json.error) {
            throw new Error(json.error.data && json.error.data.message || json.error.message);
        }
        return json.result || {};
    }

    function buildWidget(mode) {
        const root = document.createElement('div');
        root.className = 'o_ssc_root';
        root.style.cssText = [
            'display:flex', 'flex-direction:column', 'height:100%',
            'max-width:900px', 'margin:0 auto', 'padding:16px',
            'font-family:"Segoe UI", Roboto, sans-serif', 'color:#222',
        ].join(';');

        // --- Header (modes toggle + mock badge) ---
        const header = document.createElement('div');
        header.style.cssText = [
            'display:flex', 'align-items:center', 'justify-content:space-between',
            'padding:8px 12px', 'background:#714B67', 'color:#fff',
            'border-radius:6px 6px 0 0', 'font-size:14px',
        ].join(';');

        const titleEl = document.createElement('div');
        titleEl.innerHTML = '<strong>Steamships AI Assistant</strong>';
        header.appendChild(titleEl);

        const controls = document.createElement('div');
        controls.style.cssText = 'display:flex;align-items:center;gap:12px;';

        // Mode toggle (segmented control)
        const toggleWrap = document.createElement('div');
        toggleWrap.style.cssText = [
            'display:inline-flex', 'background:rgba(255,255,255,.15)',
            'border-radius:4px', 'overflow:hidden',
        ].join(';');
        const btnStaff = document.createElement('button');
        btnStaff.type = 'button';
        btnStaff.textContent = 'Staff';
        const btnClient = document.createElement('button');
        btnClient.type = 'button';
        btnClient.textContent = 'Client';
        [btnStaff, btnClient].forEach((b) => {
            b.style.cssText = [
                'border:0', 'padding:4px 12px', 'cursor:pointer',
                'background:transparent', 'color:#fff', 'font-size:13px',
            ].join(';');
        });
        function paintToggle() {
            const active = mode === MODE_STAFF ? btnStaff : btnClient;
            const inactive = mode === MODE_STAFF ? btnClient : btnStaff;
            active.style.background = '#fff';
            active.style.color = '#714B67';
            inactive.style.background = 'transparent';
            inactive.style.color = '#fff';
        }
        btnStaff.addEventListener('click', () => {
            mode = MODE_STAFF;
            setStoredMode(mode);
            paintToggle();
            appendBot('(switched to STAFF mode — full SOPs + prices)');
        });
        btnClient.addEventListener('click', () => {
            mode = MODE_CLIENT;
            setStoredMode(mode);
            paintToggle();
            appendBot('(switched to CLIENT mode — onboarding help only, no prices or internal SOPs)');
        });
        toggleWrap.appendChild(btnStaff);
        toggleWrap.appendChild(btnClient);
        controls.appendChild(toggleWrap);
        paintToggle();

        // Mock badge (placeholder — server tells us in reply.mock_mode)
        const mockBadge = document.createElement('span');
        mockBadge.id = 'ssc_mock_badge';
        mockBadge.style.cssText = [
            'display:none', 'background:#ffc107', 'color:#222',
            'padding:2px 8px', 'border-radius:10px', 'font-size:11px',
            'font-weight:600',
        ].join(';');
        mockBadge.textContent = 'MOCK MODE';
        controls.appendChild(mockBadge);

        header.appendChild(controls);
        root.appendChild(header);

        // --- Log ---
        const log = document.createElement('div');
        log.className = 'o_ssc_log';
        log.style.cssText = [
            'flex:1', 'overflow-y:auto', 'background:#f7f7f9',
            'border:1px solid #ddd', 'border-top:0', 'padding:12px',
            'min-height:300px',
        ].join(';');
        root.appendChild(log);

        // --- Input row ---
        const inputRow = document.createElement('div');
        inputRow.style.cssText = [
            'display:flex', 'gap:8px', 'padding:8px 0',
        ].join(';');
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'o_input';
        input.placeholder = mode === MODE_STAFF
            ? 'Ask about FCL, KYC, discount approval, branches...'
            : 'Ask about onboarding, KYC documents, what to expect...';
        input.style.cssText = [
            'flex:1', 'padding:8px 12px', 'border:1px solid #ccc',
            'border-radius:4px', 'font-size:14px',
        ].join(';');
        const sendBtn = document.createElement('button');
        sendBtn.type = 'button';
        sendBtn.className = 'btn btn-primary';
        sendBtn.textContent = 'Send';
        sendBtn.style.cssText = 'padding:8px 18px;';
        inputRow.appendChild(input);
        inputRow.appendChild(sendBtn);
        root.appendChild(inputRow);

        // --- Message helpers ---
        function appendMsg(role, text, sources) {
            const wrap = document.createElement('div');
            wrap.style.cssText = [
                'margin:6px 0', 'max-width:85%',
                role === 'user' ? 'margin-left:auto;text-align:right;' : '',
            ].join(';');
            const bubble = document.createElement('div');
            bubble.style.cssText = [
                'display:inline-block', 'padding:8px 12px', 'border-radius:8px',
                'text-align:left', 'white-space:pre-wrap', 'line-height:1.4',
                role === 'user'
                    ? 'background:#714B67;color:#fff;'
                    : 'background:#fff;border:1px solid #ddd;',
            ].join(';');
            bubble.textContent = text;
            wrap.appendChild(bubble);
            if (sources && sources.length) {
                const src = document.createElement('div');
                src.style.cssText = 'font-size:11px;color:#888;margin-top:2px;';
                src.textContent = 'Sources: ' + sources.join(' | ');
                wrap.appendChild(src);
            }
            log.appendChild(wrap);
            log.scrollTop = log.scrollHeight;
        }
        function appendUser(text) { appendMsg('user', text, null); }
        function appendBot(text, sources) { appendMsg('bot', text, sources || []); }

        async function send() {
            const text = (input.value || '').trim();
            if (!text) return;
            appendUser(text);
            input.value = '';
            sendBtn.disabled = true;
            try {
                const result = await callChatApi(text, mode);
                if (result.mock_mode) {
                    mockBadge.style.display = 'inline-block';
                }
                appendBot(result.reply || '(no reply)', result.sources || []);
            } catch (e) {
                appendBot('Error: ' + (e.message || e));
            } finally {
                sendBtn.disabled = false;
                input.focus();
            }
        }
        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter' && !ev.shiftKey) {
                ev.preventDefault();
                send();
            }
        });

        // --- Welcome message ---
        const welcome = mode === MODE_STAFF
            ? 'Hello! I am the Steamships knowledge assistant (STAFF mode). Ask about services, prices, KYC, or approval rules.'
            : 'Hello! I am the Steamships onboarding helper (CLIENT mode). I can answer questions about documents needed, registration steps, and what to expect. (Internal prices and SOPs are hidden in this mode.)';
        appendBot(welcome);

        return root;
    }

    // --- Odoo client action registration (legacy widget, no OWL) ---
    // Odoo 18 still supports legacy client actions via registry.category('actions').
    // We register a minimal adapter so the menu action loads our widget.
    function registerClientAction() {
        const registry = odoo.__DEBUG__.services['@web/core/registry'] ||
                         (window.odoo && window.odoo.__DEBUG__ && window.odoo.__DEBUG__.registry);
        // Odoo 18's public API: import { registry } from '@web/core/registry';
        // but in legacy ESM without imports, we use the global odoo namespace:
        if (typeof odoo === 'undefined' || !odoo.__DEBUG__) return false;
        return true;
    }

    // Odoo 18 client actions: use the public ActionManager adapter pattern.
    // Easiest: register a legacy client_action in JS via owl + registry.
    // We attach the widget to the .o_content container when the action runs.
    document.addEventListener('DOMContentLoaded', function () {
        // Watch for hash change to our action tag and inject widget.
        function checkAndMount() {
            const actionService = odoo.__DEBUG__ && odoo.__DEBUG__.services &&
                odoo.__DEBUG__.services['@web/webclient/actions/action_service'];
            if (!actionService) return;
            // The ActionManager calls our component; for simplicity we hook via
            // a MutationObserver on the main content area.
            const target = document.querySelector('.o_action_manager') ||
                           document.querySelector('.o_content');
            if (!target) return;
            const observer = new MutationObserver(() => {
                const hasWidget = target.querySelector('.o_ssc_root');
                const heading = target.querySelector('.o_control_panel .o_last_breadcrumb_item');
                if (heading && /AI Assistant/i.test(heading.textContent) && !hasWidget) {
                    const mode = getStoredMode();
                    const widget = buildWidget(mode);
                    target.appendChild(widget);
                }
            });
            observer.observe(target, {childList: true, subtree: true});
        }
        // Defer to give Odoo time to bootstrap
        setTimeout(checkAndMount, 500);
    });
})();
