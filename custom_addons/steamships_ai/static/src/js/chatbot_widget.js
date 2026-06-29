/** @odoo-module **/

(function () {
    "use strict";

    const WIDGET_ID = "steamships-ai-chatbot";
    const SUGGESTIONS = [
        "20ft container quote",
        "Onboarding documents",
        "Discount approval",
    ];

    function getCsrfToken() {
        return (window.odoo && window.odoo.csrf_token) ||
            document.querySelector("meta[name='csrf_token']")?.content ||
            "";
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function stripCommonHtml(value) {
        return String(value || "")
            .replace(/<br\s*\/?\s*>/gi, "\n")
            .replace(/<\/p>/gi, "\n")
            .replace(/<\/?(?:p|strong|b|em|ul|ol|li|h[1-6])\b[^>]*>/gi, "");
    }

    function renderMarkdownInline(value) {
        return escapeHtml(value).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    }

    function renderMarkdown(value) {
        const lines = stripCommonHtml(value).replace(/\r\n/g, "\n").split("\n");
        const html = [];
        let listType = null;

        function closeList() {
            if (listType) {
                html.push(`</${listType}>`);
                listType = null;
            }
        }

        function openList(type) {
            if (listType !== type) {
                closeList();
                html.push(`<${type} class="sai-chatbot__md-list">`);
                listType = type;
            }
        }

        lines.forEach((line) => {
            const trimmed = line.trim();
            if (!trimmed) {
                closeList();
                return;
            }

            const heading = trimmed.match(/^###\s+(.+)$/);
            if (heading) {
                closeList();
                html.push(`<h4 class="sai-chatbot__md-heading">${renderMarkdownInline(heading[1])}</h4>`);
                return;
            }

            const bullet = trimmed.match(/^[-*]\s+(.+)$/);
            if (bullet) {
                openList("ul");
                html.push(`<li>${renderMarkdownInline(bullet[1])}</li>`);
                return;
            }

            const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
            if (numbered) {
                openList("ol");
                html.push(`<li>${renderMarkdownInline(numbered[1])}</li>`);
                return;
            }

            closeList();
            html.push(`<p class="sai-chatbot__md-p">${renderMarkdownInline(trimmed)}</p>`);
        });
        closeList();
        return html.join("") || '<p class="sai-chatbot__md-p">No answer returned.</p>';
    }

    function sourceLabel(source) {
        if (typeof source === "string") {
            return source;
        }
        if (source && typeof source === "object") {
            return source.name || source.doc_name || source.filename || source.section || source.title || "Source";
        }
        return "Source";
    }

    function normaliseJsonRpcResponse(payload) {
        if (payload && Object.prototype.hasOwnProperty.call(payload, "result")) {
            return payload.result;
        }
        return payload;
    }

    class SteamshipsAIChatbot {
        constructor(root) {
            this.root = root;
            this.isOpen = false;
            this.mode = "staff";
            this.messages = root.querySelector(".sai-chatbot__messages");
            this.form = root.querySelector(".sai-chatbot__form");
            this.input = root.querySelector(".sai-chatbot__input");
            this.sendButton = root.querySelector(".sai-chatbot__send");
            this.toggleButton = root.querySelector(".sai-chatbot__launcher");
            this.panel = root.querySelector(".sai-chatbot__panel");
            this.bindEvents();
            this.addBotMessage(
                "Welcome aboard. Ask me about quotes, onboarding, approvals, or internal knowledge.",
                ["Steamships AI"]
            );
        }

        bindEvents() {
            this.toggleButton.addEventListener("click", () => this.togglePanel());
            this.root.querySelector(".sai-chatbot__close").addEventListener("click", () => this.togglePanel(false));
            this.form.addEventListener("submit", (event) => {
                event.preventDefault();
                this.ask(this.input.value);
            });
            this.root.querySelectorAll(".sai-chatbot__mode").forEach((button) => {
                button.addEventListener("click", () => this.setMode(button.dataset.mode));
            });
            this.root.querySelectorAll(".sai-chatbot__suggestion").forEach((button) => {
                button.addEventListener("click", () => this.ask(button.textContent.trim()));
            });
        }

        togglePanel(force) {
            this.isOpen = typeof force === "boolean" ? force : !this.isOpen;
            this.root.classList.toggle("is-open", this.isOpen);
            this.toggleButton.setAttribute("aria-expanded", String(this.isOpen));
            this.panel.setAttribute("aria-hidden", String(!this.isOpen));
            if (this.isOpen) {
                window.setTimeout(() => this.input.focus(), 120);
            }
        }

        setMode(mode) {
            this.mode = mode === "client" ? "client" : "staff";
            this.root.querySelectorAll(".sai-chatbot__mode").forEach((button) => {
                const active = button.dataset.mode === this.mode;
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", String(active));
            });
        }

        async ask(rawQuestion) {
            const question = String(rawQuestion || "").trim();
            if (!question) {
                this.input.focus();
                return;
            }
            this.togglePanel(true);
            this.input.value = "";
            this.addUserMessage(question);
            const typing = this.addTypingIndicator();
            this.setBusy(true);

            try {
                const response = await fetch("/steamships_ai/ask", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                    },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            question,
                            mode: this.mode,
                        },
                    }),
                });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const payload = normaliseJsonRpcResponse(await response.json());
                typing.remove();
                if (!payload || payload.ok === false) {
                    this.addBotMessage(
                        payload?.answer || "The AI service is temporarily unavailable. Please try again in a moment.",
                        [],
                        true
                    );
                    return;
                }
                this.addBotMessage(payload.answer, payload.sources || []);
            } catch (error) {
                typing.remove();
                this.addBotMessage(
                    "I could not reach the AI service right now. Please check the RAG API container and try again.",
                    [],
                    true
                );
                console.warn("Steamships AI chatbot error", error);
            } finally {
                this.setBusy(false);
            }
        }

        setBusy(isBusy) {
            this.root.classList.toggle("is-busy", isBusy);
            this.sendButton.disabled = isBusy;
            this.input.disabled = isBusy;
        }

        addUserMessage(text) {
            this.appendMessage(`
                <article class="sai-chatbot__message sai-chatbot__message--user">
                    <div class="sai-chatbot__bubble">${escapeHtml(text)}</div>
                </article>
            `);
        }

        addBotMessage(text, sources, isError = false) {
            const chips = (sources || []).slice(0, 6).map((source) => (
                `<span class="sai-chatbot__source"><strong>${escapeHtml(sourceLabel(source))}</strong></span>`
            )).join("");
            const formattedText = renderMarkdown(text);
            this.appendMessage(`
                <article class="sai-chatbot__message sai-chatbot__message--bot ${isError ? "is-error" : ""}">
                    <div class="sai-chatbot__avatar" aria-hidden="true">AI</div>
                    <div>
                        <div class="sai-chatbot__bubble sai-chatbot__markdown">${formattedText}</div>
                        ${chips ? `<div class="sai-chatbot__sources" aria-label="Sources">${chips}</div>` : ""}
                    </div>
                </article>
            `);
        }

        addTypingIndicator() {
            const wrapper = document.createElement("article");
            wrapper.className = "sai-chatbot__message sai-chatbot__message--bot sai-chatbot__typing";
            wrapper.innerHTML = `
                <div class="sai-chatbot__avatar" aria-hidden="true">AI</div>
                <div class="sai-chatbot__bubble" aria-label="AI is typing">
                    <span></span><span></span><span></span>
                </div>
            `;
            this.messages.appendChild(wrapper);
            this.scrollToBottom();
            return wrapper;
        }

        appendMessage(html) {
            this.messages.insertAdjacentHTML("beforeend", html);
            this.scrollToBottom();
        }

        scrollToBottom() {
            this.messages.scrollTop = this.messages.scrollHeight;
        }
    }

    function buildWidget() {
        const root = document.createElement("section");
        root.id = WIDGET_ID;
        root.className = "sai-chatbot";
        root.innerHTML = `
            <button class="sai-chatbot__launcher" type="button" aria-label="Ask AI" aria-expanded="false">
                <span class="sai-chatbot__launcher-icon">✦</span>
                <span>Ask AI</span>
            </button>
            <div class="sai-chatbot__panel" role="dialog" aria-label="Steamships AI assistant" aria-hidden="true">
                <header class="sai-chatbot__header">
                    <div>
                        <p class="sai-chatbot__eyebrow">Steamships Knowledge</p>
                        <h2>Ask AI</h2>
                    </div>
                    <button class="sai-chatbot__close" type="button" aria-label="Close AI chat">×</button>
                </header>
                <div class="sai-chatbot__mode-switch" role="group" aria-label="AI answer mode">
                    <button class="sai-chatbot__mode is-active" type="button" data-mode="staff" aria-pressed="true">Staff</button>
                    <button class="sai-chatbot__mode" type="button" data-mode="client" aria-pressed="false">Client</button>
                </div>
                <div class="sai-chatbot__suggestions" aria-label="Suggested questions">
                    ${SUGGESTIONS.map((text) => `<button class="sai-chatbot__suggestion" type="button">${escapeHtml(text)}</button>`).join("")}
                </div>
                <div class="sai-chatbot__messages" aria-live="polite"></div>
                <form class="sai-chatbot__form">
                    <input class="sai-chatbot__input" type="text" maxlength="2000" placeholder="Ask about freight, documents, approvals..." aria-label="Question for AI" autocomplete="off">
                    <button class="sai-chatbot__send" type="submit" aria-label="Send question">➜</button>
                </form>
            </div>
        `;
        return root;
    }

    function init() {
        if (document.getElementById(WIDGET_ID) || !document.body) {
            return;
        }
        const root = buildWidget();
        document.body.appendChild(root);
        new SteamshipsAIChatbot(root);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
