<script setup lang="ts">
import { computed, ref } from "vue";
import type { FeedbackCorrection, MessageRecord, MessageState, RequestType } from "../types";
import { ACTIONABLE_STATES } from "../types";
import { submitFeedback } from "../api";
import ImportanceBadge from "./ImportanceBadge.vue";
import StateBadge from "./StateBadge.vue";

const props = withDefaults(
  defineProps<{
    record: MessageRecord;
    busy?: boolean;
    mode?: "inbox" | "archive";
  }>(),
  { mode: "inbox" },
);

const emit = defineEmits<{
  (e: "change-state", state: MessageState): void;
  (e: "unarchive"): void;
  (e: "feedback-applied", patch: Partial<import("../types").AnalysisResult>): void;
}>();

const STATE_LABELS: Record<MessageState, string> = {
  unhandled: "未対応",
  in_progress: "対応中",
  done: "完了",
  snoozed: "保留",
  dismissed: "対象外",
};

const WEIGHT_LABELS: Record<string, string> = {
  light: "軽",
  medium: "中",
  heavy: "重",
};

const REQUEST_TYPE_LABELS: Record<string, string> = {
  reply_required: "返信",
  task_required: "作業",
  review_required: "確認",
  approval_required: "承認",
  waiting_other: "他者対応待ち",
  info_only: "情報共有",
};

// どの分析器が判定したか（説明可能性）. 未知の値はそのまま表示する.
const ANALYZER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  anthropic: "Claude",
  openai: "GPT",
  ollama: "Ollama",
  stub: "ルールベース",
};

const email = computed(() => props.record.email);
const analysis = computed(() => props.record.analysis);

const importance = computed(() => analysis.value?.importance ?? 1);
const summary = computed(() => analysis.value?.summary ?? email.value.snippet);
const requestTypeLabel = computed(() => {
  const t = analysis.value?.request_type;
  return t ? (REQUEST_TYPE_LABELS[t] ?? t) : "";
});
const weightLabel = computed(() => {
  const w = analysis.value?.task_weight;
  return w ? (WEIGHT_LABELS[w] ?? w) : "";
});
const analyzerLabel = computed(() => {
  const a = analysis.value?.analyzer;
  return a ? (ANALYZER_LABELS[a] ?? a) : "";
});

const receivedAt = computed(() => {
  const raw = email.value.received_at;
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString("ja-JP", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
});

const triage = computed(() => props.record.triage_score.toFixed(1));

const isArchive = computed(() => props.mode === "archive");

const expanded = ref(false);
const bodyText = computed(() => email.value.body_text?.trim() || null);

// 現在の状態は遷移先ボタンから除く
const nextStates = computed(() =>
  ACTIONABLE_STATES.filter((s) => s !== props.record.state),
);

// --- フィードバック ---
const feedbackOpen = ref(false);
const feedbackBusy = ref(false);
const feedbackDone = ref(false);
const feedbackError = ref<string | null>(null);

const fbForm = ref<FeedbackCorrection>({ importance: 1, request_type: "info_only", is_promotional: false, is_security_notification: false, reason: "" });

function openFeedback() {
  const a = analysis.value;
  fbForm.value = {
    importance: a?.importance ?? 3,
    request_type: (a?.request_type ?? "info_only") as RequestType,
    is_promotional: a?.is_promotional ?? false,
    is_security_notification: a?.is_security_notification ?? false,
    reason: "",
  };
  feedbackDone.value = false;
  feedbackError.value = null;
  feedbackOpen.value = true;
}

async function sendFeedback() {
  feedbackBusy.value = true;
  feedbackError.value = null;
  try {
    await submitFeedback(props.record.message_id, fbForm.value);
    feedbackDone.value = true;
    emit("feedback-applied", {
      importance: fbForm.value.importance,
      request_type: fbForm.value.request_type,
      is_promotional: fbForm.value.is_promotional,
      is_security_notification: fbForm.value.is_security_notification,
    });
    setTimeout(() => { feedbackOpen.value = false; feedbackDone.value = false; }, 1500);
  } catch (e) {
    feedbackError.value = e instanceof Error ? e.message : "送信に失敗しました";
  } finally {
    feedbackBusy.value = false;
  }
}

const REQUEST_TYPES: { value: RequestType; label: string }[] = [
  { value: "reply_required",    label: "返信" },
  { value: "task_required",     label: "作業" },
  { value: "review_required",   label: "確認" },
  { value: "approval_required", label: "承認" },
  { value: "waiting_other",     label: "他者待ち" },
  { value: "info_only",         label: "情報共有" },
];
</script>

<template>
  <article class="card" :class="{ unread: email.is_unread, archive: isArchive, expanded }">
    <div
      class="content-area"
      role="button"
      :aria-expanded="expanded"
      tabindex="0"
      @click="expanded = !expanded"
      @keydown.enter.space.prevent="expanded = !expanded"
    >
      <div class="top">
        <ImportanceBadge :importance="importance" />
        <div class="head">
          <div class="subject-row">
            <span class="subject">{{ email.subject || "(件名なし)" }}</span>
            <span v-if="email.is_unread" class="unread-dot" title="未読" aria-label="未読" />
          </div>
          <div class="meta">
            <span class="sender">{{ email.sender || "(差出人不明)" }}</span>
            <span class="dot">·</span>
            <span class="provider">{{ email.provider }}</span>
            <span v-if="receivedAt" class="dot">·</span>
            <time v-if="receivedAt">{{ receivedAt }}</time>
          </div>
        </div>
        <StateBadge :state="record.state" />
      </div>

      <p v-if="!expanded" class="summary">{{ summary }}</p>

      <div v-else class="body-expanded">
        <p v-if="bodyText" class="body-text">{{ bodyText }}</p>
        <p v-else class="summary summary-full">{{ summary }}</p>
        <p v-if="analysis?.suggested_action" class="suggested-action">
          <span class="suggested-label">提案：</span>{{ analysis.suggested_action }}
        </p>
      </div>

      <div class="tags">
        <span
          v-if="email.is_spam"
          class="tag spam"
          title="Gmail が迷惑メールに分類していました"
          >⚠️ 迷惑メール</span
        >
        <span v-if="requestTypeLabel" class="tag">{{ requestTypeLabel }}</span>
        <span v-if="weightLabel" class="tag weight">負荷 {{ weightLabel }}</span>
        <span v-if="analysis?.request_type === 'reply_required'" class="tag reply">要返信</span>
        <span
          v-if="analyzerLabel"
          class="tag analyzer"
          :title="`判定した分析器: ${analyzerLabel}`"
          >🤖 {{ analyzerLabel }}</span
        >
        <span class="tag triage" :title="`トリアージスコア ${triage}`">▲ {{ triage }}</span>
        <span class="expand-icon" :aria-hidden="true">{{ expanded ? "▲" : "▼" }}</span>
      </div>
    </div>

    <div class="actions" @click.stop>
      <template v-if="!isArchive">
        <button
          v-for="s in nextStates"
          :key="s"
          type="button"
          class="act"
          :class="`act-${s}`"
          :disabled="busy"
          @click="emit('change-state', s)"
        >
          {{ STATE_LABELS[s] }}
        </button>
      </template>
      <button
        v-else
        type="button"
        class="act act-unarchive"
        :disabled="busy"
        @click="emit('unarchive')"
      >
        復元
      </button>
      <button
        v-if="analysis"
        type="button"
        class="act act-feedback"
        :class="{ active: feedbackOpen }"
        @click="feedbackOpen ? (feedbackOpen = false) : openFeedback()"
      >
        修正
      </button>
    </div>

    <div v-if="feedbackOpen" class="feedback-panel" @click.stop>
      <p class="fb-title">判定を修正</p>

      <div class="fb-row">
        <span class="fb-label">重要度</span>
        <div class="fb-btns">
          <button
            v-for="n in [1,2,3,4,5,6]"
            :key="n"
            type="button"
            class="fb-btn"
            :class="{ selected: fbForm.importance === n, [`imp-${n}`]: true }"
            @click="fbForm.importance = n"
          >{{ n }}</button>
        </div>
      </div>

      <div class="fb-row">
        <span class="fb-label">対応区分</span>
        <div class="fb-btns wrap">
          <button
            v-for="rt in REQUEST_TYPES"
            :key="rt.value"
            type="button"
            class="fb-btn"
            :class="{ selected: fbForm.request_type === rt.value }"
            @click="fbForm.request_type = rt.value"
          >{{ rt.label }}</button>
        </div>
      </div>

      <div class="fb-row">
        <span class="fb-label">属性</span>
        <div class="fb-btns">
          <button
            type="button"
            class="fb-btn"
            :class="{ selected: fbForm.is_promotional }"
            @click="fbForm.is_promotional = !fbForm.is_promotional"
          >プロモーション</button>
          <button
            type="button"
            class="fb-btn"
            :class="{ selected: fbForm.is_security_notification }"
            @click="fbForm.is_security_notification = !fbForm.is_security_notification"
          >セキュリティ通知</button>
        </div>
      </div>

      <div v-if="feedbackDone" class="fb-notice success">送信しました</div>
      <div v-else-if="feedbackError" class="fb-notice error">{{ feedbackError }}</div>

      <div class="fb-footer">
        <button
          type="button"
          class="fb-submit"
          :disabled="feedbackBusy || feedbackDone"
          @click="sendFeedback"
        >変更を送信</button>
        <button
          type="button"
          class="fb-cancel"
          @click="feedbackOpen = false"
        >キャンセル</button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card.unread {
  border-left: 3px solid var(--accent);
}
.content-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  outline: none;
  border-radius: calc(var(--radius) - 2px);
}
.content-area:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.head {
  flex: 1;
  min-width: 0;
}
.subject-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.subject {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.unread .subject {
  font-weight: 700;
}
.unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  flex: none;
}
.meta {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 2px;
}
.sender {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 280px;
}
.dot {
  opacity: 0.5;
}
.summary {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.summary-full {
  display: block;
  -webkit-line-clamp: unset;
  line-clamp: unset;
  overflow: visible;
}
.body-expanded {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.body-text {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.suggested-action {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
.suggested-label {
  color: var(--accent);
  font-weight: 600;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 7px;
}
.tag.reply {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-weak);
}
.tag.spam {
  color: var(--danger);
  background: var(--danger-weak);
  border-color: var(--danger);
}
.tag.triage {
  color: var(--text-muted);
}
.tag.analyzer {
  color: var(--text-muted);
  font-variant: tabular-nums;
}
.expand-icon {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.5;
  user-select: none;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
.act {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
}
.act:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.act:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.act-done:hover:not(:disabled) {
  border-color: var(--success);
  color: var(--success);
}
.act-dismissed:hover:not(:disabled) {
  border-color: var(--text-muted);
  color: var(--text-muted);
}
.act-unarchive:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.card.archive {
  background: var(--bg);
  opacity: 0.85;
}
.act-feedback {
  margin-left: auto;
  color: var(--text-muted);
}
.act-feedback.active,
.act-feedback:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

/* フィードバックパネル */
.feedback-panel {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.fb-title {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.fb-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.fb-label {
  font-size: 12px;
  color: var(--text-muted);
  width: 60px;
  flex-shrink: 0;
  padding-top: 3px;
}
.fb-btns {
  display: flex;
  gap: 4px;
}
.fb-btns.wrap {
  flex-wrap: wrap;
}
.fb-btn {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
  transition: border-color 0.1s, color 0.1s, background 0.1s;
}
.fb-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.fb-btn.selected {
  border-color: var(--accent);
  background: var(--accent-weak);
  color: var(--accent);
  font-weight: 600;
}
.fb-btn.imp-4.selected { border-color: var(--warning); background: var(--warning-weak); color: var(--warning); }
.fb-btn.imp-5.selected { border-color: var(--danger); background: var(--danger-weak); color: var(--danger); }
.fb-btn.imp-6.selected { border-color: #7f1d1d; background: #fee2e2; color: #7f1d1d; }
.fb-footer {
  display: flex;
  gap: 6px;
}
.fb-submit {
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 4px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}
.fb-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.fb-cancel {
  font-size: 12px;
  padding: 5px 14px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-muted);
}
.fb-cancel:hover {
  border-color: var(--text-muted);
}
.fb-notice {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
}
.fb-notice.success {
  background: var(--success-weak);
  color: var(--success);
}
.fb-notice.error {
  background: var(--danger-weak);
  color: var(--danger);
}
</style>
