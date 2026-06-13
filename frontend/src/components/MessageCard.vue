<script setup lang="ts">
import { computed, ref } from "vue";
import type { MessageRecord, MessageState } from "../types";
import { ACTIONABLE_STATES } from "../types";
import ImportanceBadge from "./ImportanceBadge.vue";
import StateBadge from "./StateBadge.vue";

const props = withDefaults(
  defineProps<{
    record: MessageRecord;
    busy?: boolean;
    mode?: "inbox" | "archive";
    priority?: boolean;
  }>(),
  { mode: "inbox", priority: false },
);

const emit = defineEmits<{
  (e: "change-state", state: MessageState): void;
  (e: "unarchive"): void;
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

const email = computed(() => props.record.email);
const analysis = computed(() => props.record.analysis);

const importance = computed(() => analysis.value?.importance ?? 1);
const level = computed(() => Math.min(5, Math.max(1, importance.value)));
const summary = computed(() => analysis.value?.summary ?? email.value.snippet);
const category = computed(() => analysis.value?.category ?? "");
const weightLabel = computed(() => {
  const w = analysis.value?.task_weight;
  return w ? (WEIGHT_LABELS[w] ?? w) : "";
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
</script>

<template>
  <article
    class="card-msg"
    :class="{ priority, archive: isArchive, expanded }"
  >
    <div
      class="content-area"
      role="button"
      :aria-expanded="expanded"
      tabindex="0"
      @click="expanded = !expanded"
      @keydown.enter.space.prevent="expanded = !expanded"
    >
      <div class="head-row">
        <ImportanceBadge :importance="importance" />
        <span class="subject" :class="`stroke-${level}`">
          {{ email.subject || "(件名なし)" }}
        </span>
        <span
          v-if="email.is_unread"
          class="unread-dot"
          title="未読"
          aria-label="未読"
        />
        <StateBadge :state="record.state" class="state-chip" />
      </div>

      <div class="meta-row">
        <span class="sender">{{ email.sender || "(差出人不明)" }}</span>
        <span class="sep" aria-hidden="true">·</span>
        <span class="provider">{{ email.provider }}</span>
        <time v-if="receivedAt" class="stamp num">{{ receivedAt }}</time>
      </div>

      <p v-if="!expanded" class="summary">{{ summary }}</p>

      <div v-else class="body-expanded">
        <p v-if="bodyText" class="body-text">{{ bodyText }}</p>
        <p v-else class="summary summary-full">{{ summary }}</p>
        <p v-if="analysis?.suggested_action" class="suggested-action">
          <span class="suggested-label">提案</span>{{ analysis.suggested_action }}
        </p>
      </div>
    </div>

    <div class="foot-row">
      <div class="tags">
        <span v-if="category" class="tag">{{ category }}</span>
        <span v-if="weightLabel" class="tag">負荷 {{ weightLabel }}</span>
        <span v-if="analysis?.needs_reply" class="tag reply">要返信</span>
        <span class="tag num" :title="`トリアージスコア ${triage}`">▲ {{ triage }}</span>
        <span class="expand-icon" aria-hidden="true">{{ expanded ? "とじる" : "ひらく" }}</span>
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
      </div>
    </div>
  </article>
</template>

<style scoped>
.card-msg {
  background: var(--card);
  border-radius: var(--radius-card);
  box-shadow: var(--elev-1);
  padding: var(--space-4) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  transition: transform var(--duration-micro) var(--ease-spring),
    box-shadow var(--duration-micro) var(--ease-spring);
}
.card-msg:hover {
  transform: translateY(-2px);
  box-shadow: var(--elev-2);
}
/* Signature ゾーンのカードは常に浮いている */
.card-msg.priority {
  box-shadow: var(--elev-2);
}
.card-msg.archive {
  background: color-mix(in srgb, var(--card) 70%, var(--wall));
  box-shadow: none;
  border: 1.5px solid var(--line);
}

.content-area {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  cursor: pointer;
  outline: none;
  border-radius: var(--radius-inset);
}
.content-area:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--fl-cyan) 60%, white);
  outline-offset: 2px;
}

.head-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
/* 件名＝蛍光マーカーのストローク（色は重要度ランプ） */
.subject {
  font-size: var(--text-16);
  font-weight: 700;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  padding: 0 var(--space-1);
}
.stroke-1 {
  background: linear-gradient(transparent 60%, var(--fl-cyan-stroke) 60%, var(--fl-cyan-stroke) 94%, transparent 94%);
}
.stroke-2 {
  background: linear-gradient(transparent 60%, var(--fl-green-stroke) 60%, var(--fl-green-stroke) 94%, transparent 94%);
}
.stroke-3 {
  background: linear-gradient(transparent 60%, var(--fl-yellow-stroke) 60%, var(--fl-yellow-stroke) 94%, transparent 94%);
}
.stroke-4 {
  background: linear-gradient(transparent 60%, var(--fl-orange-stroke) 60%, var(--fl-orange-stroke) 94%, transparent 94%);
}
.stroke-5 {
  background: linear-gradient(transparent 60%, var(--fl-magenta-stroke) 60%, var(--fl-magenta-stroke) 94%, transparent 94%);
}
.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fl-cyan);
  flex: none;
}
.state-chip {
  margin-left: auto;
  flex: none;
}

.meta-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--text-12);
  color: var(--ink-soft);
  padding-left: 42px; /* blob 30px + gap 12px に揃える */
}
.sender {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}
.sep {
  color: var(--ink-faint);
}
.stamp {
  margin-left: auto;
  flex: none;
  color: var(--ink-soft);
}

.summary {
  margin: 0;
  color: var(--ink-soft);
  font-size: var(--text-12);
  padding-left: 42px;
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
  gap: var(--space-2);
  margin: var(--space-2) 0 0 42px;
}
.body-text {
  margin: 0;
  color: var(--ink);
  font-size: var(--text-12);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  max-height: 400px;
  overflow-y: auto;
  padding: var(--space-3) var(--space-4);
  background: var(--card-inset);
  border-radius: var(--radius-inset);
}
.suggested-action {
  margin: 0;
  font-size: var(--text-12);
  color: var(--ink-soft);
}
.suggested-label {
  display: inline-block;
  background: var(--fl-cyan-tint);
  color: var(--ink);
  font-weight: 700;
  border-radius: var(--radius-pill);
  padding: 1px var(--space-2);
  margin-right: var(--space-2);
}

.foot-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding-left: 42px;
}
.tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1);
  min-width: 0;
}
.tag {
  font-size: var(--text-12);
  color: var(--ink-soft);
  background: var(--card-inset);
  border-radius: var(--radius-pill);
  padding: 1px var(--space-3);
}
.tag.reply {
  color: var(--ink);
  background: var(--fl-magenta-tint);
  font-weight: 700;
}
.expand-icon {
  font-size: var(--text-12);
  color: var(--ink-faint);
  user-select: none;
  padding: 0 var(--space-1);
}

.actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.act {
  font-size: var(--text-12);
  font-weight: 500;
  padding: 3px var(--space-3);
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--line);
  background: transparent;
  color: var(--ink-soft);
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth),
    border-color var(--duration-micro) var(--ease-smooth);
}
.act:hover:not(:disabled) {
  background: var(--card-inset);
  color: var(--ink);
  border-color: var(--ink-faint);
}
.act:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.act-done:hover:not(:disabled) {
  background: var(--fl-green-tint);
  border-color: var(--fl-green);
  color: var(--ink);
}
.act-in_progress:hover:not(:disabled) {
  background: var(--fl-cyan-tint);
  border-color: var(--fl-cyan);
  color: var(--ink);
}
.act-snoozed:hover:not(:disabled) {
  background: var(--fl-yellow-tint);
  border-color: color-mix(in srgb, var(--fl-yellow) 80%, var(--ink));
  color: var(--ink);
}
.act-unhandled:hover:not(:disabled) {
  background: var(--fl-orange-tint);
  border-color: var(--fl-orange);
  color: var(--ink);
}
.act-unarchive:hover:not(:disabled) {
  background: var(--fl-cyan-tint);
  border-color: var(--fl-cyan);
  color: var(--ink);
}
</style>
