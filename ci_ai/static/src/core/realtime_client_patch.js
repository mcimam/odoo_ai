/** @odoo-module **/

import RealtimeClient from "@ai/core/realtime_client";
import { AITranscriptionEvent, transcriptionBus } from "@ai/core/transcription_bus";
import { patch } from "@web/core/utils/patch";

/**
 * OpenAI gpt-live-transcribe needs:
 * - WebSocket URL with intent=transcription
 * - client-side input_audio_buffer.commit (no server_vad)
 * - synthetic usage on completion events (stock UI assumes usage exists)
 *
 * IAP still uses the stock URL + server_vad; only enable this when the session
 * RPC returns ci_ai_realtime=true.
 */
patch(RealtimeClient.prototype, {
    connect(sessionToken, options = {}) {
        this._ciAiRealtime = Boolean(options?.ciAiRealtime);
        this._removeCiAiSocketListeners();

        const wsUrl = this._ciAiRealtime
            ? "wss://api.openai.com/v1/realtime?intent=transcription"
            : "wss://api.openai.com/v1/realtime";
        this.socket = new WebSocket(wsUrl, [
            "realtime",
            `openai-insecure-api-key.${sessionToken}`,
        ]);

        if (this._ciAiRealtime) {
            this._ciAiMessageListener = (event) => {
                const jsonData = JSON.parse(event.data);
                if (
                    jsonData.type === "conversation.item.input_audio_transcription.completed" &&
                    !jsonData.usage
                ) {
                    jsonData.usage = {
                        input_token_details: { text_tokens: 0, audio_tokens: 0 },
                        output_tokens: 0,
                        duration: 0,
                    };
                }
                transcriptionBus.trigger(AITranscriptionEvent.REALTIME_CLIENT_MESSAGE, jsonData);
            };
            this.socket.addEventListener("message", this._ciAiMessageListener);
        } else {
            this.socket.addEventListener("message", this.messageListener);
        }
    },

    /**
     * Commit the current input audio buffer so gpt-live-transcribe finalizes
     * the turn (required when turn_detection is null).
     */
    commit() {
        if (this.socket !== null && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ type: "input_audio_buffer.commit" }));
        }
    },

    _removeCiAiSocketListeners() {
        if (this.socket) {
            if (this._ciAiMessageListener) {
                this.socket.removeEventListener("message", this._ciAiMessageListener);
            }
            this.socket.removeEventListener("message", this.messageListener);
        }
        this._ciAiMessageListener = null;
    },

    disconnect() {
        this._removeCiAiSocketListeners();
        this._ciAiRealtime = false;
        if (this.socket !== null) {
            this.socket.close();
            this.socket = null;
        }
    },
});
