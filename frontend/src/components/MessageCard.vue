<script setup lang="ts">
import { computed, ref } from "vue";
import type { FeedbackCorrection, MessageRecord, MessageState, RequestType } from "../types";
import { submitFeedback } from "../api";
import ImportanceBadge from "./ImportanceBadge.vue";
import StateBadge from "./StateBadge.vue";

const props = withDefaults(
  defineProps<{
    record: MessageRecord;
    busy?: boolean;
    mode?: "inbox" | "archive";
    compact?: boolean;
    focused?: boolean;
    selected?: boolean;
    searchQuery?: string;
  }>(),
  { mode: "inbox", compact: false, focused: false, selected: false, searchQuery: "" },
);

function highlight(text: string): string {
  const q = props.searchQuery?.trim();
  if (!q) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const escapedQ = escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return escaped.replace(new RegExp(escapedQ, "gi"), (m) => `<mark class="hl">${m}</mark>`);
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const emit = defineEmits<{
  (e: "change-state", state: MessageState): void;
  (e: "archive"): void;
  (e: "unarchive"): void;
  (e: "toggle-select"): void;
  (e: "feedback-applied", patch: Partial<import("../types").AnalysisResult>): void;
}>();

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

const ANALYZER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  anthropic: "Claude",
  openai: "GPT",
  ollama: "Ollama",
  stub: "ルールベース",
};

const email = computed(() => props.record.email);
const analysis = computed(() => props.record.analysis);

const avatarInitials = computed(() => {
  const sender = email.value.sender || "";
  const name = sender.replace(/<[^>]+>/, "").trim() || sender;
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0][0].toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
});

// 送信者文字列のハッシュで5色パレットの4色から決定的に選ぶ
// mist(#E4EBF2) と white は地と被るため除外し、ocean/leaf/sand/sage の4色のみ使用
const AVATAR_COLORS = ["var(--ocean)", "var(--leaf)", "var(--sand)", "var(--sage)"] as const;
const avatarColor = computed(() => {
  const str = email.value.sender || "?";
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
  const idx = ((hash % AVATAR_COLORS.length) + AVATAR_COLORS.length) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
});

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
  const diff = Date.now() - d.getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins < 1)   return "たった今";
  if (mins < 60)  return `${mins}分前`;
  if (hours < 24) return `${hours}時間前`;
  if (days < 2)   return "昨日";
  if (days < 7)   return `${days}日前`;
  return d.toLocaleDateString("ja-JP", { month: "short", day: "numeric" });
});

const receivedAtFull = computed(() => {
  const raw = email.value.received_at;
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString("ja-JP", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
});

const triage = computed(() => props.record.triage_score.toFixed(1));

const isArchive = computed(() => props.mode === "archive");

const expanded = ref(false);
const bodyText = computed(() => email.value.body_text?.trim() || null);

const bodyHtml = computed(() => {
  const raw = bodyText.value;
  if (!raw) return null;
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const linked = escaped.replace(
    /(https?:\/\/[^\s<>"']+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  return linked.replace(/\n/g, "<br>");
});

// 重要度5以上は件名を強調（5=緑 / 6＝最重要=青）
const isTopImportance = computed(() => importance.value >= 5);
const isMaxImportance = computed(() => importance.value >= 6);

// プロバイダ（アプリ）ごとにカードの縁色を変える
const providerClass = computed(() => `card--${(email.value.provider || "").toLowerCase()}`);

// ── オーバーフローメニュー ──
// 主要アクション: done（✓完了）・snoozed（⏸保留）
// 残りは ⋯ メニューへ: in_progress・dismissed（archive）
const overflowOpen = ref(false);

function toggleOverflow(e: MouseEvent | KeyboardEvent) {
  e.stopPropagation();
  overflowOpen.value = !overflowOpen.value;
}

function closeOverflow() {
  overflowOpen.value = false;
}

// ⋯メニューが開いている状態で外部クリックで閉じる（document listener）
function handleOverflowBlur(e: FocusEvent) {
  const related = e.relatedTarget as HTMLElement | null;
  // フォーカスがオーバーフローメニュー内に留まる場合は閉じない
  if (related && related.closest(".overflow-menu")) return;
  overflowOpen.value = false;
}

// 状態遷移ハンドラ（emit は既存のまま）
function onChangeState(s: MessageState) {
  closeOverflow();
  emit("change-state", s);
}

function onArchive() {
  closeOverflow();
  emit("archive");
}

// ── フィードバック（判定の修正） ──
const feedbackOpen = ref(false);
const feedbackBusy = ref(false);
const feedbackDone = ref(false);
const feedbackError = ref<string | null>(null);

const fbForm = ref<FeedbackCorrection>({
  importance: 1,
  request_type: "info_only",
  is_promotional: false,
  is_security_notification: false,
  reason: "",
});

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

function toggleFeedback() {
  if (feedbackOpen.value) {
    feedbackOpen.value = false;
  } else {
    openFeedback();
  }
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
  <article
    class="card glass"
    :class="[providerClass, {
      unread: email.is_unread,
      archive: isArchive,
      expanded,
      compact: props.compact,
      focused: props.focused,
      selected: props.selected,
    }]"
    :style="{ '--imp-color': `var(--imp-${importance})` }"
  >
    <!--
      左アクセントバー（::before）は CSS で定義．
      .glass::after は鏡面ハイライト層なので z-index で content-area が上に来る
    -->

    <div
      class="content-area"
      role="button"
      :aria-expanded="expanded"
      tabindex="0"
      @click="expanded = !expanded"
      @keydown.enter.space.prevent="expanded = !expanded"
    >
      <!-- ── Row 1: アバター・差出人・時刻・状態ピル・未読ドット ── -->
      <div class="top">
        <!-- アバター（サイコロ風 rounded-square） -->
        <div
          class="avatar-wrap"
          :title="email.sender || ''"
          @click.stop="emit('toggle-select')"
        >
          <div
            class="avatar"
            :style="{ background: avatarColor }"
            aria-hidden="true"
          >{{ avatarInitials }}</div>
          <div class="avatar-check" :class="{ checked: props.selected }" aria-hidden="true">
            <svg v-if="props.selected" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
        </div>

        <!-- 差出人・ch・時刻 -->
        <div class="meta-row">
          <span class="sender" v-html="highlight(email.sender || '(差出人不明)')" />
          <span class="dot" aria-hidden="true">·</span>
          <span class="provider">{{ email.provider }}</span>
          <span v-if="receivedAt" class="dot" aria-hidden="true">·</span>
          <time v-if="receivedAt" class="received" :title="receivedAtFull" :datetime="email.received_at ?? undefined">{{ receivedAt }}</time>
        </div>

        <!-- 右端: 状態ピル + 未読ドット -->
        <div class="top-right">
          <StateBadge :state="record.state" />
          <span v-if="email.is_unread" class="unread-dot" title="未読" aria-label="未読" />
        </div>
      </div>

      <!-- ── Row 2: 件名 + 重要度サイコロ ── -->
      <div class="subject-row">
        <span
          class="subject"
          :class="{ 'subject--top': isTopImportance, 'subject--max': isMaxImportance }"
          v-html="highlight(email.subject || '(件名なし)')"
        />
        <ImportanceBadge :importance="importance" />
      </div>

      <!-- ── Row 3: 要約 1〜2行クランプ ── -->
      <p v-if="!expanded && !props.compact" class="summary" v-html="highlight(summary)" />

      <!-- ── 展開: 本文 ── -->
      <Transition name="expand">
        <div v-if="expanded" class="body-expanded">
          <div v-if="bodyHtml" class="body-text" v-html="bodyHtml" />
          <p v-else class="summary summary-full">{{ summary }}</p>
          <p v-if="analysis?.suggested_action" class="suggested-action">
            <span class="suggested-label">提案：</span>{{ analysis.suggested_action }}
          </p>
        </div>
      </Transition>

      <!-- ── Row 4: タグ群 + 展開アイコン ── -->
      <div v-if="!props.compact" class="tags">
        <span
          v-if="email.is_spam"
          class="tag tag--spam"
          title="Gmail が迷惑メールに分類していました"
          >⚠️ 迷惑メール</span
        >
        <span v-if="requestTypeLabel" class="tag">{{ requestTypeLabel }}</span>
        <span v-if="weightLabel" class="tag">負荷 {{ weightLabel }}</span>
        <span v-if="analysis?.request_type === 'reply_required'" class="tag tag--reply">要返信</span>
        <span
          v-if="analysis?.is_security_notification"
          class="tag tag--security"
          title="セキュリティ通知"
          >🔒 セキュリティ</span
        >
        <span
          v-if="analyzerLabel"
          class="tag"
          :title="`判定した分析器: ${analyzerLabel}`"
          >🤖 {{ analyzerLabel }}</span
        >
        <span class="tag tag--triage triage-tip">
          ▲ {{ triage }}
          <span class="triage-tooltip" role="tooltip">
            <span class="triage-row">重要度 {{ importance }} / 6</span>
            <span v-if="analysis?.request_type === 'reply_required'" class="triage-row">要返信</span>
            <span v-if="analysis?.deadline" class="triage-row">期限：{{ analysis.deadline.slice(0, 10) }}</span>
            <span v-if="weightLabel" class="triage-row">タスク負荷：{{ weightLabel }}</span>
            <span v-if="analyzerLabel" class="triage-row">判定：{{ analyzerLabel }}</span>
          </span>
        </span>
        <span class="expand-icon" aria-hidden="true">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline :points="expanded ? '18 15 12 9 6 15' : '6 9 12 15 18 9'" />
          </svg>
        </span>
      </div>
    </div>

    <!-- ── アクション行 ── -->
    <div class="actions" @click.stop>
      <!-- アーカイブ済み: 復元のみ -->
      <template v-if="isArchive">
        <button
          type="button"
          class="act act--unarchive"
          :disabled="busy"
          title="受信トレイに戻す"
          aria-label="受信トレイに戻す"
          @click="emit('unarchive')"
        >
          復元
        </button>
      </template>

      <!-- 受信トレイ: 主要2個 + ⋯ オーバーフロー -->
      <template v-else>
        <!-- ✓ 完了 -->
        <button
          type="button"
          class="act act--done"
          :class="{ 'act--active': record.state === 'done' }"
          :disabled="busy"
          title="完了にする"
          aria-label="完了にする"
          @click="onChangeState(record.state === 'done' ? 'unhandled' : 'done')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          完了
        </button>

        <!-- ⏸ 保留 -->
        <button
          type="button"
          class="act act--snoozed"
          :class="{ 'act--active': record.state === 'snoozed' }"
          :disabled="busy"
          title="保留にする"
          aria-label="保留にする"
          @click="onChangeState(record.state === 'snoozed' ? 'unhandled' : 'snoozed')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
          </svg>
          保留
        </button>

        <!-- ⋯ オーバーフローメニュー -->
        <div class="overflow-wrap">
          <button
            type="button"
            class="act act--overflow"
            :disabled="busy"
            :aria-expanded="overflowOpen"
            aria-haspopup="true"
            title="その他の操作"
            aria-label="その他の操作"
            @click="toggleOverflow"
            @keydown.esc="closeOverflow"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true">
              <circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>
            </svg>
          </button>

          <Transition name="menu">
            <div
              v-if="overflowOpen"
              class="overflow-menu glass"
              role="menu"
              @focusout="handleOverflowBlur"
            >
              <!-- 対応中に戻す -->
              <button
                type="button"
                class="menu-item"
                :class="{ 'menu-item--active': record.state === 'in_progress' }"
                role="menuitem"
                :disabled="busy"
                @click="onChangeState(record.state === 'in_progress' ? 'unhandled' : 'in_progress')"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                </svg>
                {{ record.state === 'in_progress' ? '未対応に戻す' : '対応中にする' }}
              </button>

              <!-- 対象外（archive） -->
              <button
                type="button"
                class="menu-item menu-item--dismiss"
                role="menuitem"
                :disabled="busy"
                @click="onArchive"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>
                </svg>
                対象外にする
              </button>
            </div>
          </Transition>
        </div>
      </template>

      <!-- 判定の修正（フィードバック） -->
      <button
        v-if="analysis"
        type="button"
        class="act act--feedback"
        :class="{ 'act--active': feedbackOpen }"
        :disabled="busy"
        title="判定を修正する"
        aria-label="判定を修正する"
        @click="toggleFeedback"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
        </svg>
        修正
      </button>
    </div>

    <!-- ── フィードバックパネル ── -->
    <Transition name="expand">
      <div v-if="feedbackOpen" class="feedback-panel" @click.stop>
        <p class="fb-title">判定を修正</p>

        <div class="fb-row">
          <span class="fb-label">重要度</span>
          <div class="fb-btns">
            <button
              v-for="n in [1, 2, 3, 4, 5, 6]"
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
          <div class="fb-btns wrap">
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

        <div class="fb-row">
          <span class="fb-label">メモ</span>
          <input
            v-model="fbForm.reason"
            type="text"
            class="fb-input"
            maxlength="300"
            placeholder="修正理由（任意・学習に利用）"
          />
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
    </Transition>
  </article>
</template>

<style scoped>
/*
 * MessageCard — ダッシュボード型 × Apple Liquid Glass
 * パレット: 5色（mist/ocean/sage/leaf/sand）＋白のみ
 * 文字は常に ocean（var(--text)/var(--ocean)）．濃色塗り面上のみ白
 * ダークモードなし（html.dark セレクタ禁止）
 * DESIGN.md §0〜§7・§A-5 準拠
 */

/* ── カード本体 ── */
.card {
  padding: 14px 16px 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition:
    box-shadow var(--dur-base) var(--ease-out-expo),
    transform var(--dur-base) var(--ease-spring);
  position: relative;
  will-change: transform;
}

/* カードは「不透明な白」にして，半透明ガラスの中間レイヤー（背景が透けて
   オレンジに色付く層）を排除する．背景と白いカードだけが見える状態にする．
   （.card.glass で global .glass より高い詳細度で上書き） */
.card.glass {
  background: var(--white);
  -webkit-backdrop-filter: none;
  backdrop-filter: none;
  /* アプリ（プロバイダ）ごとに縁色を変える．既定は sage */
  border: 4px solid var(--sage);
  /* 静止時は影なし＝境界はカード縁の1本だけ（影が作る2本目の境目を排除） */
  box-shadow: none;
  border-radius: var(--radius);
}
/* フロストの鏡面反射層も不要（白カードなので） */
.card.glass::after {
  display: none;
}

/* プロバイダ別の縁色（アプリの違いを一目で） */
.card--gmail.glass   { border-color: var(--ocean); } /* Google → 青 */
.card--github.glass  { border-color: var(--leaf); }  /* GitHub → 緑 */
.card--slack.glass   { border-color: var(--sand); }  /* Slack → 黄 */
.card--outlook.glass { border-color: var(--sage); }  /* Outlook → 鼠 */

/* hover：派手に弾んで持ち上がる（枠/影は出さず・白いまま） */
.card:hover {
  box-shadow: none;
  transform: translateY(-7px) scale(1.015);
}
.card:active {
  transform: translateY(-2px) scale(0.995);
}

.card.compact {
  padding: 8px 16px 8px 20px;
  gap: 0;
}
.card.compact .content-area {
  gap: 0;
}
.card.compact.expanded .content-area {
  gap: 8px;
}

/* アーカイブ状態: ガラスを薄く・控えめ */
.card.archive {
  opacity: 0.82;
}

/* フォーカス: WCAG 2.1 AA（ocean 55%） */
.card.focused {
  outline: 3px solid rgba(4, 157, 191, 0.55);
  outline-offset: 2px;
}

/* 選択状態 */
/* 選択時：青いリング/色付けはしない（選択はアバターのチェックで示す） */
.card.selected {
  box-shadow: none;
}

/* ── コンテンツエリア ── */
.content-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  outline: none;
  border-radius: calc(var(--radius) - 4px);
  /* .glass::after (z-index:0) より上に来るよう z-index 設定 */
  position: relative;
  z-index: 2;
}
.content-area:focus-visible {
  outline: 3px solid rgba(4, 157, 191, 0.55);
  outline-offset: 2px;
}

/* ── Row 1: アバター・差出人・時刻・状態ピル ── */
.top {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── アバター（サイコロ風 rounded square） ── */
.avatar-wrap {
  position: relative;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  cursor: pointer;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: var(--white);
  letter-spacing: 0.02em;
  transition: opacity var(--dur-fast) var(--ease-spring);
}
.avatar-check {
  position: absolute;
  inset: 0;
  border-radius: 8px;
  background: var(--mist);
  border: 2px solid var(--sage);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition:
    opacity var(--dur-fast) var(--ease-spring),
    background var(--dur-fast) var(--ease-out-expo),
    border-color var(--dur-fast) var(--ease-out-expo);
  color: var(--white);
}
.avatar-check.checked {
  background: var(--ocean);
  border-color: var(--ocean);
  opacity: 1;
}
.avatar-wrap:hover .avatar-check:not(.checked) {
  opacity: 1;
}
.card.selected .avatar-check {
  opacity: 1;
}
.avatar-wrap:hover .avatar,
.card.selected .avatar {
  opacity: 0;
}

/* 差出人・ch・時刻（flex 1 で件名の幅を確保） */
.meta-row {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
  min-width: 0;
  color: var(--text-muted);
  font-size: 12px;
  overflow: hidden;
}
.sender {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.provider {
  white-space: nowrap;
}
.received {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.dot {
  opacity: 0.4;
  flex-shrink: 0;
}

/* 右端: 状態ピル + 未読ドット */
.top-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ocean);
  flex: none;
}

/* ── Row 2: 件名 + 重要度サイコロ ── */
.subject-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.subject {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
  /* 文字幅に合わせる（マーカーが文字を超えて端まで伸びないように） */
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
}
/* 重要度サイコロは常に右端へ */
.subject-row :deep(.imp) {
  margin-left: auto;
  flex-shrink: 0;
}
/* コンパクト表示時はサイコロを小さく（キツキツ回避・狭い画面対策） */
.card.compact :deep(.imp svg) {
  width: 30px;
  height: 30px;
}
.unread .subject {
  font-weight: 700;
}

/* 重要度5以上: 文字は青のまま・太字＋ sand 蛍光マーカー（5も6も黄色） */
.subject--top {
  font-weight: 700;
  background: linear-gradient(transparent 62%, var(--sand) 62%);
  border-radius: 1px;
  padding: 0 2px 2px;
}

/* ── Row 3: 要約 ── */
.summary {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.55;
}
.summary-full {
  display: block;
  -webkit-line-clamp: unset;
  line-clamp: unset;
  overflow: visible;
}

/* ── 展開本文 ── */
.body-expanded {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: -4px;
}
.body-text {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  word-break: break-word;
  line-height: 1.65;
  max-height: 400px;
  overflow-y: auto;
  padding: 10px 12px;
  background: rgba(228, 235, 242, 0.55);
  border: 1px solid var(--sage);
  border-radius: var(--radius-sm);
}
.body-text :deep(a) {
  color: var(--ocean);
  text-decoration: underline;
  word-break: break-all;
}
.suggested-action {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}
.suggested-label {
  color: var(--ocean);
  font-weight: 600;
}

/* ── Row 4: タグ群 ── */
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
}

/* 基本タグ: mist/白淡地＋sage枠＋ocean文字 pill */
.tag {
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(228, 235, 242, 0.55);
  border: 1px solid var(--sage);
  border-radius: var(--radius-pill);
  padding: 2px 9px;
  transition: transform var(--dur-fast) var(--ease-spring);
}
.tag:hover {
  transform: translateY(-1px) scale(1.03);
}

/* 要返信: ocean 強調（ocean-12地＋ocean枠＋ocean文字＋weight600） */
.tag--reply {
  color: var(--ocean);
  border-color: var(--ocean);
  background: var(--ocean-12);
  font-weight: 600;
}

/* 迷惑メール: sand 強調で注意喚起 */
.tag--spam {
  color: var(--ocean);
  border-color: var(--sand);
  background: var(--sand-weak);
  font-weight: 600;
}

/* セキュリティ通知: leaf 強調 */
.tag--security {
  color: var(--ocean);
  border-color: var(--leaf);
  background: var(--leaf-weak);
  font-weight: 600;
}

/* triage スコア */
.tag--triage {
  color: var(--text-muted);
}

/* triage ツールチップ: 濃ガラス（ocean地＋白文字） */
.triage-tip {
  position: relative;
  cursor: default;
}
.triage-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--ocean);
  color: var(--white);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  font-size: 11px;
  white-space: nowrap;
  z-index: 200;
  flex-direction: column;
  gap: 3px;
  box-shadow: var(--glass-shadow-hover);
  pointer-events: none;
}
.triage-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--ocean);
}
.triage-tip:hover .triage-tooltip {
  display: flex;
}
.triage-row {
  display: block;
  line-height: 1.5;
}

.expand-icon {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.45;
  user-select: none;
  transition: transform var(--dur-base) var(--ease-spring);
}
/* expanded 状態のアイコン: 上向き矢印は SVG points で制御済み．
   scale でほんのり pop して切り替えを知覚しやすくする */
.card.expanded .expand-icon {
  transform: scale(1.05);
}

/* ── アクション行 ── */
.actions {
  display: flex;
  align-items: center;
  gap: 6px;
  border-top: 1px solid rgba(174, 191, 188, 0.35);
  padding-top: 10px;
  position: relative;
  z-index: 2;
}
.card.compact .actions {
  padding-top: 6px;
}

/* 基本ボタン共通 */
.act {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(174, 191, 188, 0.55);
  background: rgba(255, 255, 255, 0.55);
  color: var(--text-muted);
  transition:
    border-color var(--dur-fast) var(--ease-out-expo),
    background var(--dur-fast) var(--ease-out-expo),
    color var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-spring);
  white-space: nowrap;
}
.act:hover:not(:disabled) {
  border-color: var(--ocean);
  color: var(--ocean);
  background: var(--ocean-12);
  transform: translateY(-1px) scale(1.03);
}
.act:active:not(:disabled) {
  transform: scale(0.94);
}
.act:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ✓ 完了 */
.act--done:hover:not(:disabled),
.act--done.act--active {
  border-color: var(--leaf);
  color: var(--ocean);
  background: var(--leaf-weak);
}
.act--done.act--active {
  font-weight: 600;
}

/* ⏸ 保留 */
.act--snoozed:hover:not(:disabled),
.act--snoozed.act--active {
  border-color: var(--sage);
  color: var(--ocean);
  background: var(--sage-weak);
}
.act--snoozed.act--active {
  font-weight: 600;
}

/* 復元ボタン（アーカイブ時） */
.act--unarchive:hover:not(:disabled) {
  border-color: var(--ocean);
  color: var(--ocean);
  background: var(--ocean-12);
}

/* ✎ 修正（フィードバック）: 右端に寄せる */
.act--feedback {
  margin-left: auto;
}
.act--feedback:hover:not(:disabled),
.act--feedback.act--active {
  border-color: var(--ocean);
  color: var(--ocean);
  background: var(--ocean-12);
}
.act--feedback.act--active {
  font-weight: 600;
}

/* ⋯ オーバーフロートリガー（アイコンボタン: scale のみ） */
.act--overflow {
  padding: 4px 8px;
}
.act--overflow:hover:not(:disabled) {
  transform: scale(1.15);
}
.act--overflow:active:not(:disabled) {
  transform: scale(0.9);
}

/* ── オーバーフローメニュー ── */
.overflow-wrap {
  position: relative;
  margin-left: auto;
}

/* ガラスメニュー本体（.glass は backdrop-filter を担う） */
.overflow-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  right: 0;
  min-width: 152px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 300;
  /* .glass が border-radius を設定するが上書きして小さめに */
  border-radius: var(--radius-sm) !important;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 7px 10px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  text-align: left;
  transition:
    background var(--dur-fast) var(--ease-out-expo),
    color var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-spring);
  white-space: nowrap;
}
.menu-item:hover:not(:disabled) {
  background: var(--ocean-12);
  color: var(--ocean);
  transform: translateY(-1px) scale(1.03);
}
.menu-item:active:not(:disabled) {
  transform: scale(0.94);
}
.menu-item--active {
  color: var(--ocean);
  background: var(--ocean-08);
  font-weight: 600;
}
.menu-item--dismiss:hover:not(:disabled) {
  background: var(--sage-weak);
  color: var(--ocean);
}
.menu-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ── メニュー出現アニメーション（fade + translateY/scale, out-expo） ── */
.menu-enter-active {
  transition:
    opacity var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-spring);
}
.menu-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-out-expo);
}
.menu-enter-from,
.menu-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.94);
}

/* ── 検索ハイライト: sand地＋ocean文字（黄色禁止） ── */
:deep(.hl) {
  background: var(--sand);
  color: var(--ocean);
  border-radius: 2px;
  padding: 0 1px;
}

/* ── 展開アニメーション（opacity + transform, out-expo で統一） ── */
.expand-enter-active {
  transition:
    opacity var(--dur-base) var(--ease-out-expo),
    transform var(--dur-base) var(--ease-spring);
}
.expand-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-out-expo);
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(-6px) scaleY(0.94);
  transform-origin: top;
}

/* ── フィードバックパネル（判定の修正） ── */
.feedback-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid rgba(174, 191, 188, 0.35);
  padding-top: 12px;
  margin-top: 2px;
}
.fb-title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.fb-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.fb-label {
  font-size: 12px;
  color: var(--text-muted);
  width: 64px;
  flex-shrink: 0;
  padding-top: 5px;
}
.fb-btns {
  display: flex;
  gap: 5px;
}
.fb-btns.wrap {
  flex-wrap: wrap;
}
.fb-btn {
  font-size: 12px;
  padding: 4px 11px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(174, 191, 188, 0.55);
  background: rgba(255, 255, 255, 0.55);
  color: var(--text-muted);
  transition:
    border-color var(--dur-fast) var(--ease-out-expo),
    background var(--dur-fast) var(--ease-out-expo),
    color var(--dur-fast) var(--ease-out-expo),
    transform var(--dur-fast) var(--ease-spring);
}
.fb-btn:hover {
  border-color: var(--ocean);
  color: var(--ocean);
  transform: translateY(-1px) scale(1.03);
}
.fb-btn.selected {
  border-color: var(--ocean);
  background: var(--ocean-12);
  color: var(--ocean);
  font-weight: 600;
}
/* 重要度ボタン選択時は段階色で塗り分け（imp パレット準拠） */
.fb-btn.imp-4.selected { border-color: var(--imp-4); background: var(--sand-weak); }
.fb-btn.imp-5.selected { border-color: var(--imp-5); background: var(--leaf-weak); }
.fb-btn.imp-6.selected { border-color: var(--imp-6); background: var(--sand-strong); }

.fb-input {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(174, 191, 188, 0.55);
  background: rgba(255, 255, 255, 0.6);
  color: var(--text);
}
.fb-input:focus {
  outline: none;
  border-color: var(--ocean);
}
.fb-notice {
  font-size: 12px;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
}
.fb-notice.success {
  background: var(--leaf-weak);
  color: var(--ocean);
  font-weight: 600;
}
.fb-notice.error {
  background: var(--ocean-12);
  color: var(--ocean);
}
.fb-footer {
  display: flex;
  gap: 6px;
}
.fb-submit {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 16px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--ocean);
  background: var(--ocean);
  color: var(--white);
  transition:
    transform var(--dur-fast) var(--ease-spring),
    opacity var(--dur-fast) var(--ease-out-expo);
}
.fb-submit:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.03);
}
.fb-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.fb-cancel {
  font-size: 12px;
  padding: 6px 16px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(174, 191, 188, 0.55);
  background: rgba(255, 255, 255, 0.55);
  color: var(--text-muted);
  transition: border-color var(--dur-fast) var(--ease-out-expo);
}
.fb-cancel:hover {
  border-color: var(--ocean);
  color: var(--ocean);
}
</style>
