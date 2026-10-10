/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

/**
 * If bus already delivered ready during /ai/start_session_advance, do not let the
 * RPC acknowledgement regress the session back to waiting_model (stuck Thinking).
 */
patch(Thread.prototype, {
    async requestAiSessionAdvance(route, body) {
        if (route === "/ai/start_session_advance" && this.channel) {
            this.channel._ciAiCompletedDuringSubmit = false;
        }
        const acknowledgement = await super.requestAiSessionAdvance(route, body);
        if (
            route === "/ai/start_session_advance" &&
            acknowledgement?.loop_state === "waiting_model" &&
            this.channel?._ciAiCompletedDuringSubmit
        ) {
            const session = body.session_id
                ? this.store["ai.session"].get(body.session_id)
                : this.channel?.aiRootSession;
            if (session?.exists()) {
                session.loop_state = "ready";
                session.syncAiSessionState();
            }
        }
        return acknowledgement;
    },
});
