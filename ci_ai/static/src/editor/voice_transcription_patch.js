/** @odoo-module **/

import { VoiceTranscription } from "@ai/editor/embedded_components/core/voice_transcription";
import { AITranscriptionEvent, transcriptionBus } from "@ai/core/transcription_bus";
import { rpc, RPCError } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";

/**
 * Adapt live voice transcription for OpenAI gpt-live-transcribe:
 * - Pass ci_ai_realtime into RealtimeClient.connect
 * - Commit audio on client VAD silence / stop
 * - Surface status=error from /ai/transcription/session
 */
patch(VoiceTranscription.prototype, {
    setup() {
        super.setup(...arguments);
        this._ciAiRealtime = false;

        useBus(transcriptionBus, AITranscriptionEvent.AUDIO_PROCESSOR_STATE, (event) => {
            if (!this._ciAiRealtime || this.state.status !== "recording") {
                return;
            }
            if (event.detail === "stopped") {
                this.realtimeClient.commit();
            }
        });
    },

    async toggleRecording() {
        this.state.isRecording = !this.state.isRecording;
        if (this.state.status === "idle") {
            const transcriptPrompt = this.descendants.notesContent;
            try {
                this.state.status = "waiting";
                const response = await rpc("/ai/transcription/session", {
                    language: this.state.currentLanguage.shortCode,
                    prompt: transcriptPrompt?.innerText.trim(),
                });
                if (response.status === "success") {
                    await this.resetIAPTracking();
                    this.iapTransactionToken = response.iap_transaction_token || null;
                    this._ciAiRealtime = Boolean(response.ci_ai_realtime);
                    this.realtimeClient.connect(response.session_token, {
                        ciAiRealtime: this._ciAiRealtime,
                    });
                    this.state.status = "recording";
                    this.props.onTranscriptionStarted(
                        this.descendants.transcriptContent,
                        this.state.currentLanguage.code.replace("_", "-")
                    );
                    await this.audioProcessor.start();
                    this.setCurrentTab("transcript");
                } else if (response.status === "insufficient_credit") {
                    this.state.status = "idle";
                    this.state.isRecording = false;
                } else if (response.status === "error") {
                    this.state.status = "idle";
                    this.state.isRecording = false;
                    this.notificationService.add(
                        response.message || _t("Unable to start the recording."),
                        {
                            title: _t("An error occurred"),
                            type: "danger",
                        }
                    );
                } else {
                    this.state.status = "idle";
                    this.state.isRecording = false;
                    this.notificationService.add(_t("Unable to start the recording."), {
                        title: _t("An error occurred"),
                        type: "danger",
                    });
                }
            } catch (error) {
                this._ciAiRealtime = false;
                this.state.status = "idle";
                this.state.isRecording = false;
                if (error instanceof DOMException && error.name === "NotAllowedError") {
                    this.notificationService.add(
                        _t(
                            "You must allow the access to your microphone to start the recording. Try refreshing the page and start again."
                        ),
                        {
                            title: _t("Access error"),
                            type: "danger",
                        }
                    );
                } else if (error instanceof RPCError && error.data.name === "odoo.exceptions.UserError") {
                    this.notificationService.add(error.data.message, {
                        type: "danger",
                    });
                } else {
                    this.notificationService.add(_t("Unable to start the recording."), {
                        title: _t("An error occurred"),
                        type: "danger",
                    });
                }
            }
        } else if (this.state.status === "recording") {
            if (this._ciAiRealtime) {
                this.realtimeClient.commit();
            }
            await this.resetIAPTracking();
            this.audioProcessor.stop();
            this.realtimeClient.disconnect();
            this._ciAiRealtime = false;
            this.props.onTranscriptionUpdated("stopped", this.descendants.transcriptContent);
            this.updateSummary();
        }
    },
});
