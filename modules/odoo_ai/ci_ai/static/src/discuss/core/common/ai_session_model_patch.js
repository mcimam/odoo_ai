/** @odoo-module **/

import { AiSession, isAiResponseInProgress } from "@ai/discuss/core/common/ai_session_model";
import { patch } from "@web/core/utils/patch";

/**
 * Fast BYO providers can finish (bus → ready) before /ai/start_session_advance
 * returns. The stock client then applies acknowledgement.loop_state=waiting_model
 * and the UI sticks on "Thinking". Track in-progress→ready during submit.
 */
patch(AiSession.prototype, {
    setup() {
        super.setup(...arguments);
        this._ciAiPrevLoopState = this.loop_state;
        this.onChange(
            () => [this.loop_state],
            function onCiAiLoopStateChange() {
                const channel = this.channel_id;
                if (
                    channel?.isAiSubmitting &&
                    !this.parent_session_id &&
                    isAiResponseInProgress(this._ciAiPrevLoopState) &&
                    this.loop_state === "ready"
                ) {
                    channel._ciAiCompletedDuringSubmit = true;
                }
                this._ciAiPrevLoopState = this.loop_state;
            },
            { immediate: true, initialRun: false },
        );
    },
});
