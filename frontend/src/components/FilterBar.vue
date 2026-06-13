<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick } from "vue";
import type { MessagesQuery } from "../api";
import type { AccountConfig } from "../types";

// ────────────────────────────────────────────────────────
// Props / Emits
// ────────────────────────────────────────────────────────
const props = defineProps<{
  modelValue: MessagesQuery;
  providers: string[];
  accounts: AccountConfig[];
  selectedAccounts: string[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: MessagesQuery];
  "toggle-account": [address: string];
}>();

function patch(updates: Partial<MessagesQuery>): void {
  emit("update:modelValue", { ...props.modelValue, ...updates });
}

// ────────────────────────────────────────────────────────
// §1 並べ替え — セグメンテッドコントロール
// ────────────────────────────────────────────────────────
type SortColumn = "triage_score" | "importance" | "received_at";

interface SortSegment {
  order_by: SortColumn;
  label: string;
  ariaLabel: string;
}

const SORT_SEGMENTS: SortSegment[] = [
  { order_by: "triage_score", label: "推奨度",   ariaLabel: "推奨度で並べ替え" },
  { order_by: "importance",   label: "重要度",   ariaLabel: "重要度で並べ替え" },
  { order_by: "received_at",  label: "受信日時", ariaLabel: "受信日時で並べ替え" },
];

const sortColumn = computed<SortColumn>(() =>
  (props.modelValue.order_by as SortColumn | undefined) ?? "triage_score"
);
const sortDesc = computed<boolean>(() => props.modelValue.descending ?? true);

function selectSortColumn(col: SortColumn): void {
  if (sortColumn.value === col) {
    // 同じ列をクリック → 昇降を反転
    patch({ order_by: col, descending: !sortDesc.value });
  } else {
    // 新しい列 → 降順をデフォルト
    patch({ order_by: col, descending: true });
  }
}

function toggleSortDir(): void {
  patch({ descending: !sortDesc.value });
}

function sortSegmentKeydown(e: KeyboardEvent, col: SortColumn, idx: number): void {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    selectSortColumn(col);
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    const next = SORT_SEGMENTS[(idx + 1) % SORT_SEGMENTS.length];
    selectSortColumn(next.order_by);
    // フォーカス移動
    const btns = sortGroupRef.value?.querySelectorAll<HTMLButtonElement>(".sort-btn");
    btns?.[(idx + 1) % SORT_SEGMENTS.length]?.focus();
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    const prev = SORT_SEGMENTS[(idx - 1 + SORT_SEGMENTS.length) % SORT_SEGMENTS.length];
    selectSortColumn(prev.order_by);
    const btns = sortGroupRef.value?.querySelectorAll<HTMLButtonElement>(".sort-btn");
    btns?.[(idx - 1 + SORT_SEGMENTS.length) % SORT_SEGMENTS.length]?.focus();
  }
}

const sortGroupRef = ref<HTMLElement | null>(null);

// ────────────────────────────────────────────────────────
// §2 重要度しきい値 — サイコロ1〜5タップ
// ────────────────────────────────────────────────────────

// pip positions for dice faces 1-6 (within 20x20 viewBox)
interface Pip { cx: number; cy: number }
const DICE_PIPS: Record<number, Pip[]> = {
  1: [{ cx: 10, cy: 10 }],
  2: [{ cx: 5.5, cy: 5.5 }, { cx: 14.5, cy: 14.5 }],
  3: [{ cx: 5.5, cy: 5.5 }, { cx: 10, cy: 10 }, { cx: 14.5, cy: 14.5 }],
  4: [{ cx: 5.5, cy: 5.5 }, { cx: 14.5, cy: 5.5 }, { cx: 5.5, cy: 14.5 }, { cx: 14.5, cy: 14.5 }],
  5: [{ cx: 5.5, cy: 5.5 }, { cx: 14.5, cy: 5.5 }, { cx: 10, cy: 10 }, { cx: 5.5, cy: 14.5 }, { cx: 14.5, cy: 14.5 }],
  6: [
    { cx: 5.5, cy: 5 }, { cx: 5.5, cy: 10 }, { cx: 5.5, cy: 15 },
    { cx: 14.5, cy: 5 }, { cx: 14.5, cy: 10 }, { cx: 14.5, cy: 15 },
  ],
};

// 表示順：左ほど高い重要度（降順）．後で 6 を分析側に追加予定
const IMPORTANCE_FACES = [6, 5, 4, 3, 2, 1];

const importanceMin = computed<number>(() => props.modelValue.importance_min ?? 0);

function setImportanceMin(val: number): void {
  patch({ importance_min: val > 0 ? val : undefined });
}

// 並びに依存しない（DOM 兄弟でフォーカス移動）キーボード操作
function diceKeydown(e: KeyboardEvent, face: number): void {
  const btn = e.currentTarget as HTMLElement;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    setImportanceMin(importanceMin.value === face ? 0 : face);
  } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    (btn.nextElementSibling as HTMLElement | null)?.focus();
  } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    (btn.previousElementSibling as HTMLElement | null)?.focus();
  }
}

const diceFocusRef = ref<HTMLElement | null>(null);

// ────────────────────────────────────────────────────────
// §3 受信日時 — トリガーチップ＋カレンダーポップオーバー
// ────────────────────────────────────────────────────────
const afterPopoverOpen = ref(false);
const beforePopoverOpen = ref(false);
const afterInputRef = ref<HTMLInputElement | null>(null);
const beforeInputRef = ref<HTMLInputElement | null>(null);
const afterTriggerRef = ref<HTMLElement | null>(null);
const beforeTriggerRef = ref<HTMLElement | null>(null);
const afterPopoverRef = ref<HTMLElement | null>(null);
const beforePopoverRef = ref<HTMLElement | null>(null);

function toDateInput(iso: string | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

function formatDateLabel(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function openAfterPopover(): void {
  beforePopoverOpen.value = false;
  afterPopoverOpen.value = true;
  nextTick(() => { afterInputRef.value?.focus(); });
}
function closeAfterPopover(): void { afterPopoverOpen.value = false; }

function openBeforePopover(): void {
  afterPopoverOpen.value = false;
  beforePopoverOpen.value = true;
  nextTick(() => { beforeInputRef.value?.focus(); });
}
function closeBeforePopover(): void { beforePopoverOpen.value = false; }

function setReceivedAfter(e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  patch({ received_after: v ? `${v}T00:00:00Z` : undefined });
  if (v) closeAfterPopover();
}

function setReceivedBefore(e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  patch({ received_before: v ? `${v}T23:59:59Z` : undefined });
  if (v) closeBeforePopover();
}

function clearAfter(e: Event): void {
  e.stopPropagation();
  patch({ received_after: undefined });
  afterPopoverOpen.value = false;
}

function clearBefore(e: Event): void {
  e.stopPropagation();
  patch({ received_before: undefined });
  beforePopoverOpen.value = false;
}

// click outside handler for popovers
function handleDocClick(e: MouseEvent): void {
  const target = e.target as Node;
  if (
    afterPopoverOpen.value &&
    !afterTriggerRef.value?.contains(target) &&
    !afterPopoverRef.value?.contains(target)
  ) {
    closeAfterPopover();
  }
  if (
    beforePopoverOpen.value &&
    !beforeTriggerRef.value?.contains(target) &&
    !beforePopoverRef.value?.contains(target)
  ) {
    closeBeforePopover();
  }
}

function popoverKeydown(e: KeyboardEvent, which: "after" | "before"): void {
  if (e.key === "Escape") {
    if (which === "after") { closeAfterPopover(); afterTriggerRef.value?.focus(); }
    else { closeBeforePopover(); beforeTriggerRef.value?.focus(); }
  }
}

onMounted(() => { document.addEventListener("mousedown", handleDocClick); });
onUnmounted(() => { document.removeEventListener("mousedown", handleDocClick); });

// ────────────────────────────────────────────────────────
// §4 未読のみ — トグルチップ（role="switch"）
// ────────────────────────────────────────────────────────
const unreadOnly = computed<boolean>(() => props.modelValue.unread_only ?? false);

function toggleUnreadOnly(): void {
  patch({ unread_only: unreadOnly.value ? undefined : true });
}

// ────────────────────────────────────────────────────────
// §5 アカウント source — マルチセレクトチップ
// ────────────────────────────────────────────────────────
function toggleAccount(address: string): void {
  emit("toggle-account", address);
}
function isAccountSelected(address: string): boolean {
  return props.selectedAccounts.includes(address);
}

// プロバイダ表示名
const PROVIDER_NAMES: Record<string, string> = {
  gmail: "Gmail",
  github: "GitHub",
  slack: "Slack",
  outlook: "Outlook",
};

// アカウントをプロバイダ（アプリ）ごとにグループ化
const groupedAccounts = computed(() => {
  const groups = new Map<string, { provider: string; name: string; accounts: AccountConfig[] }>();
  for (const acc of props.accounts) {
    const key = acc.provider.toLowerCase();
    if (!groups.has(key)) {
      groups.set(key, { provider: key, name: PROVIDER_NAMES[key] ?? acc.provider, accounts: [] });
    }
    groups.get(key)!.accounts.push(acc);
  }
  return [...groups.values()];
});

// ────────────────────────────────────────────────────────
// §6 サマリーバー / クリア
// ────────────────────────────────────────────────────────
</script>

<template>
  <div class="filter-bar">

    <!-- ══════════════════════════════
         §1 並べ替え — セグメンテッドコントロール
         ══════════════════════════════ -->
    <section class="filter-section" aria-labelledby="sort-label">
      <div class="sort-header">
        <div id="sort-label" class="section-label">並べ替え</div>
        <!-- 昇降トグル（「並べ替え」ラベルの右隣） -->
        <button
          type="button"
          class="dir-toggle"
          :aria-label="sortDesc ? '昇順に切り替え' : '降順に切り替え'"
          :title="sortDesc ? '昇順に切り替え' : '降順に切り替え'"
          @click="toggleSortDir"
        >
          <span :class="sortDesc ? 'dir-icon--desc' : 'dir-icon--asc'" aria-hidden="true">
            {{ sortDesc ? "↓" : "↑" }}
          </span>
          <span class="dir-toggle-label">{{ sortDesc ? "降順" : "昇順" }}</span>
        </button>
      </div>
      <div
        ref="sortGroupRef"
        class="segment-group"
        role="group"
        aria-label="並べ替え列の選択"
      >
        <button
          v-for="(seg, idx) in SORT_SEGMENTS"
          :key="seg.order_by"
          type="button"
          class="sort-btn"
          :class="{ 'sort-btn--active': sortColumn === seg.order_by }"
          :aria-pressed="sortColumn === seg.order_by"
          :aria-label="seg.ariaLabel + (sortColumn === seg.order_by ? (sortDesc ? '降順' : '昇順') : '')"
          :tabindex="sortColumn === seg.order_by || (idx === 0 && !SORT_SEGMENTS.some((s, i) => i !== idx && sortColumn === s.order_by)) ? 0 : -1"
          @click="selectSortColumn(seg.order_by)"
          @keydown="sortSegmentKeydown($event, seg.order_by, idx)"
        >
          {{ seg.label }}
        </button>
      </div>
    </section>

    <!-- ══════════════════════════════
         アカウント — アプリ（プロバイダ）ごとにグループ表示
         ══════════════════════════════ -->
    <template v-if="accounts.length > 1">
      <div class="divider" role="separator" aria-hidden="true" />
      <section class="filter-section" aria-labelledby="account-label">
        <div id="account-label" class="section-label">アカウント</div>
        <div
          v-for="group in groupedAccounts"
          :key="group.provider"
          class="account-group"
        >
          <span class="account-provider-name">{{ group.name }}:</span>
          <div class="account-chips" role="group" :aria-label="`${group.name} のアカウントで絞り込み`">
            <button
              v-for="acc in group.accounts"
              :key="acc.id"
              type="button"
              class="account-chip"
              :class="{ 'account-chip--active': isAccountSelected(acc.address) }"
              :aria-pressed="isAccountSelected(acc.address)"
              :aria-label="`${acc.label || acc.provider} でフィルター${isAccountSelected(acc.address) ? '（選択中）' : ''}`"
              @click="toggleAccount(acc.address)"
            >
              {{ acc.label || acc.provider }}
              <span
                v-if="isAccountSelected(acc.address)"
                class="chip-x"
                aria-hidden="true"
              >×</span>
            </button>
          </div>
        </div>
      </section>
    </template>

    <div class="divider" role="separator" aria-hidden="true" />

    <!-- ══════════════════════════════
         §2 重要度 — サイコロ1〜5タップ
         ══════════════════════════════ -->
    <section class="filter-section" aria-labelledby="imp-label">
      <div id="imp-label" class="section-label">重要度</div>
      <div class="dice-row" ref="diceFocusRef">
        <div
          role="radiogroup"
          aria-label="重要度しきい値（選択した数以上を表示）"
          class="dice-group"
        >
          <button
            v-for="face in IMPORTANCE_FACES"
            :key="face"
            type="button"
            class="dice-face"
            :class="{
              'dice-face--selected': importanceMin === face,
              'dice-face--gte': importanceMin > 0 && face >= importanceMin,
              [`dice-face--imp${face}`]: true,
            }"
            role="radio"
            :aria-checked="importanceMin === face"
            :aria-label="`重要度${face}以上`"
            @click="setImportanceMin(importanceMin === face ? 0 : face)"
            @keydown="diceKeydown($event, face)"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" class="dice-svg">
              <circle
                v-for="(pip, pi) in DICE_PIPS[face]"
                :key="pi"
                :cx="pip.cx"
                :cy="pip.cy"
                r="1.8"
                class="pip"
              />
            </svg>
          </button>
        </div>
      </div>
      <div class="dice-hint" aria-live="polite">
        <template v-if="importanceMin === 0">すべて表示</template>
        <template v-else>重要度 {{ importanceMin }} 以上を表示</template>
      </div>
    </section>

    <div class="divider" role="separator" aria-hidden="true" />

    <!-- ══════════════════════════════
         §3 受信日時 — チップ＋ポップオーバー
         ══════════════════════════════ -->
    <section class="filter-section" aria-labelledby="date-label">
      <div id="date-label" class="section-label">受信日時</div>
      <div class="date-chips-row">

        <!-- After チップ -->
        <div class="date-chip-wrap">
          <button
            ref="afterTriggerRef"
            type="button"
            class="date-chip"
            :class="{ 'date-chip--active': !!modelValue.received_after }"
            :aria-expanded="afterPopoverOpen"
            aria-haspopup="dialog"
            aria-controls="after-popover"
            :aria-label="modelValue.received_after
              ? `after: ${formatDateLabel(modelValue.received_after)}、変更`
              : '受信日時（from）を設定'"
            @click="afterPopoverOpen ? closeAfterPopover() : openAfterPopover()"
          >
            <span v-if="modelValue.received_after">
              after: {{ formatDateLabel(modelValue.received_after) }}
            </span>
            <span v-else class="date-placeholder">from…</span>
            <button
              v-if="modelValue.received_after"
              type="button"
              class="chip-clear-btn"
              aria-label="after フィルターを解除"
              @click="clearAfter"
            >×</button>
          </button>

          <!-- After ポップオーバー -->
          <Transition name="popover">
            <div
              v-if="afterPopoverOpen"
              id="after-popover"
              ref="afterPopoverRef"
              class="date-popover glass"
              role="dialog"
              aria-modal="false"
              aria-label="受信日時（from）を選択"
              @keydown="popoverKeydown($event, 'after')"
            >
              <div class="popover-label">from（以降）</div>
              <input
                ref="afterInputRef"
                type="date"
                class="popover-date-input"
                :value="toDateInput(modelValue.received_after)"
                aria-label="受信日時 from"
                @change="setReceivedAfter"
              />
              <button
                type="button"
                class="popover-close-btn"
                aria-label="閉じる"
                @click="closeAfterPopover"
              >閉じる</button>
            </div>
          </Transition>
        </div>

        <!-- Before チップ -->
        <div class="date-chip-wrap">
          <button
            ref="beforeTriggerRef"
            type="button"
            class="date-chip"
            :class="{ 'date-chip--active': !!modelValue.received_before }"
            :aria-expanded="beforePopoverOpen"
            aria-haspopup="dialog"
            aria-controls="before-popover"
            :aria-label="modelValue.received_before
              ? `before: ${formatDateLabel(modelValue.received_before)}、変更`
              : '受信日時（to）を設定'"
            @click="beforePopoverOpen ? closeBeforePopover() : openBeforePopover()"
          >
            <span v-if="modelValue.received_before">
              before: {{ formatDateLabel(modelValue.received_before) }}
            </span>
            <span v-else class="date-placeholder">to…</span>
            <button
              v-if="modelValue.received_before"
              type="button"
              class="chip-clear-btn"
              aria-label="before フィルターを解除"
              @click="clearBefore"
            >×</button>
          </button>

          <!-- Before ポップオーバー -->
          <Transition name="popover">
            <div
              v-if="beforePopoverOpen"
              id="before-popover"
              ref="beforePopoverRef"
              class="date-popover glass"
              role="dialog"
              aria-modal="false"
              aria-label="受信日時（to）を選択"
              @keydown="popoverKeydown($event, 'before')"
            >
              <div class="popover-label">to（以前）</div>
              <input
                ref="beforeInputRef"
                type="date"
                class="popover-date-input"
                :value="toDateInput(modelValue.received_before)"
                aria-label="受信日時 to"
                @change="setReceivedBefore"
              />
              <button
                type="button"
                class="popover-close-btn"
                aria-label="閉じる"
                @click="closeBeforePopover"
              >閉じる</button>
            </div>
          </Transition>
        </div>

      </div>
    </section>

    <div class="divider" role="separator" aria-hidden="true" />

    <!-- ══════════════════════════════
         §4 未読のみ — トグルチップ
         ══════════════════════════════ -->
    <section class="filter-section" aria-labelledby="unread-label">
      <div id="unread-label" class="section-label">未読</div>
      <button
        type="button"
        class="toggle-chip"
        :class="{ 'toggle-chip--on': unreadOnly }"
        role="switch"
        :aria-checked="unreadOnly"
        aria-label="未読メッセージのみを表示"
        @click="toggleUnreadOnly"
        @keydown.space.prevent="toggleUnreadOnly"
      >
        <span class="toggle-track" aria-hidden="true">
          <span class="toggle-thumb"></span>
        </span>
        <span class="toggle-text">未読のみ</span>
      </button>
    </section>

  </div>
</template>

<style scoped>
/* ── ベースレイアウト ── */
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
}

.filter-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 並べ替え：ラベル行に降順トグルを右寄せで同居させる */
.sort-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ocean);
  user-select: none;
}

.divider {
  height: 1px;
  background: var(--sage-weak);
  margin: 0;
}

/* ── §6 サマリーバー ── */
.summary-bar {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 10px;
  background: var(--ocean-08);
  border: 1px solid var(--ocean-20);
  border-radius: var(--radius-sm);
  font-size: 11px;
}

.summary-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ocean);
  padding-top: 1px;
  flex-shrink: 0;
}

.summary-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ocean);
  background: var(--ocean-12);
  border: 1px solid var(--ocean-20);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out-expo),
              transform var(--dur-fast) var(--ease-spring);
}
.summary-chip:hover {
  background: var(--ocean-20);
  transform: scale(1.04);
}
.summary-chip:active {
  transform: scale(0.96);
}

.clear-all-btn {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--ocean);
  background: none;
  border: none;
  padding: 2px 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  flex-shrink: 0;
}
.clear-all-btn:hover {
  opacity: 0.75;
}

/* summary-bar トランジション */
.summary-bar-enter-active {
  animation: pop-in 150ms var(--ease-spring) both;
}
.summary-bar-leave-active {
  animation: pop-in 120ms var(--ease-out-expo) reverse both;
}

/* ── §1 セグメンテッドコントロール ── */
.segment-group {
  display: flex;
  gap: 4px;
  background: var(--mist);
  border: 1px solid var(--sage-weak);
  border-radius: var(--radius-pill);
  padding: 3px;
}

.sort-btn {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ocean);
  background: transparent;
  border: none;
  border-radius: var(--radius-pill);
  padding: 5px 6px;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out-expo),
              color var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
  white-space: nowrap;
}
.sort-btn:hover:not(.sort-btn--active) {
  background: var(--ocean-08);
  color: var(--ocean);
}
.sort-btn:active {
  transform: scale(0.95);
}
.sort-btn--active {
  background: var(--ocean);
  color: var(--white);
  font-weight: 700;
  box-shadow: 0 2px 8px var(--ocean-20);
}

.sort-dir-badge {
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.dir-toggle {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  color: var(--ocean);
  background: var(--ocean-08);
  border: 1px solid var(--ocean-20);
  border-radius: var(--radius-pill);
  padding: 5px 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
}
.dir-toggle:hover {
  background: var(--ocean-12);
}
.dir-toggle:active {
  transform: scale(0.95);
}

.dir-icon--desc,
.dir-icon--asc {
  font-size: 14px;
  line-height: 1;
}

.dir-toggle-label {
  font-size: 11px;
}

/* ── §2 サイコロ ── */
.dice-row {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
}

.dice-group {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: nowrap;
  gap: 5px;
}

.dice-all-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--ocean);
  background: var(--mist);
  border: 1.5px solid var(--sage-weak);
  cursor: pointer;
  flex-shrink: 0;
  transition: background var(--dur-fast) var(--ease-out-expo),
              color var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dice-all-btn:hover:not(.dice-all-btn--active) {
  background: var(--ocean-08);
  color: var(--ocean);
  border-color: var(--ocean-20);
}
.dice-all-btn:active {
  transform: scale(0.90);
}
.dice-all-btn--active {
  background: var(--ocean);
  color: var(--white);
  border-color: var(--ocean);
}

.dice-face {
  flex: 1 1 0;
  min-width: 0;
  max-width: 34px;
  aspect-ratio: 1 / 1;
  border-radius: 5px;
  border: 1.5px solid var(--sage-weak);
  background: var(--mist);
  cursor: pointer;
  padding: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo),
              transform 150ms var(--ease-spring),
              box-shadow var(--dur-fast) var(--ease-out-expo);
}
.dice-face:hover {
  border-color: var(--ocean-20);
  background: var(--ocean-08);
  transform: translateY(-2px) scale(1.06);
  box-shadow: 0 6px 14px var(--ocean-12);
}
.dice-face:active {
  transform: scale(0.94);
}

/* 重要度ランプ — face ごとに pip 色が変わる */
.dice-face--imp1 .pip { fill: var(--sage); }
.dice-face--imp2 .pip { fill: var(--ocean-50); }
.dice-face--imp3 .pip { fill: var(--ocean-72); }
.dice-face--imp4 .pip { fill: var(--ocean); }
.dice-face--imp5 .pip { fill: var(--ocean); }
.dice-face--imp6 .pip { fill: var(--ocean); }

/* しきい値以上に選択されている面 */
.dice-face--gte {
  border-color: var(--ocean-20);
  background: var(--ocean-08);
}

/* 選択されている面（=importanceMin） */
.dice-face--selected {
  background: var(--ocean) !important;
  border-color: var(--ocean) !important;
  box-shadow: 0 4px 12px var(--ocean-20);
  transform: translateY(-3px) !important;
}
.dice-face--selected .pip { fill: var(--white) !important; }

/* 最高値（imp6）の sand halo */
.dice-face--imp6.dice-face--selected {
  box-shadow: 0 4px 12px var(--ocean-20), 0 0 0 3px rgba(242, 212, 155, 0.55);
}

.dice-svg {
  width: 100%;
  height: 100%;
}

.dice-hint {
  font-size: 11px;
  color: var(--ocean);
  min-height: 16px;
}

/* ── §3 日付チップ＋ポップオーバー ── */
.date-chips-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.date-chip-wrap {
  position: relative;
}

.date-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ocean);
  background: var(--mist);
  border: 1.5px solid var(--sage-weak);
  border-radius: var(--radius-pill);
  padding: 5px 12px;
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: background var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
}
.date-chip:hover {
  background: var(--ocean-08);
  border-color: var(--ocean-20);
}
.date-chip:active {
  transform: scale(0.97);
}
.date-chip--active {
  background: var(--ocean-12);
  border-color: var(--ocean-20);
  font-weight: 600;
}

.date-placeholder {
  color: var(--ocean);
  font-style: italic;
}

.chip-clear-btn {
  margin-left: auto;
  font-size: 13px;
  font-weight: 700;
  color: var(--ocean);
  background: none;
  border: none;
  padding: 0 0 0 4px;
  cursor: pointer;
  line-height: 1;
  flex-shrink: 0;
  transition: color var(--dur-fast);
}
.chip-clear-btn:hover {
  color: var(--ocean);
}

/* ポップオーバー */
.date-popover {
  position: absolute;
  left: 0;
  top: calc(100% + 6px);
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  min-width: 180px;
  /* glass はグローバルユーティリティ適用済み */
  border-radius: var(--radius-sm) !important;
}

.popover-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--ocean);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.popover-date-input {
  font-size: 13px;
  font-family: inherit;
  color: var(--ocean);
  background: var(--mist);
  border: 1.5px solid var(--sage-weak);
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  width: 100%;
  transition: border-color var(--dur-fast);
}
.popover-date-input:focus {
  border-color: var(--ocean);
  outline: 3px solid var(--ocean-12);
  outline-offset: 1px;
}

.popover-close-btn {
  font-size: 11px;
  font-weight: 600;
  color: var(--ocean);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-align: right;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.popover-close-btn:hover {
  opacity: 0.75;
}

/* ポップオーバー トランジション */
.popover-enter-active {
  animation: popover-in 150ms var(--ease-out-expo) both;
}
.popover-leave-active {
  animation: popover-in 120ms var(--ease-out-expo) reverse both;
}
@keyframes popover-in {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* ── §4 トグルチップ（role="switch"） ── */
.toggle-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ocean);
  background: var(--mist);
  border: 1.5px solid var(--sage-weak);
  border-radius: var(--radius-pill);
  padding: 5px 12px;
  cursor: pointer;
  align-self: flex-start;
  transition: background var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
}
.toggle-chip:hover {
  background: var(--ocean-08);
  border-color: var(--ocean-20);
}
.toggle-chip:active {
  transform: scale(0.95);
}
.toggle-chip--on {
  background: var(--ocean);
  border-color: var(--ocean);
  color: var(--white);
}

.toggle-track {
  position: relative;
  width: 26px;
  height: 14px;
  border-radius: var(--radius-pill);
  background: var(--sage-weak);
  border: 1px solid var(--sage);
  flex-shrink: 0;
  transition: background var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo);
}
.toggle-chip--on .toggle-track {
  background: rgba(255, 255, 255, 0.35);
  border-color: rgba(255, 255, 255, 0.45);
}
.toggle-thumb {
  position: absolute;
  top: 1px;
  left: 1px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--sage);
  transition: transform var(--dur-fast) var(--ease-spring),
              background var(--dur-fast) var(--ease-out-expo);
}
.toggle-chip--on .toggle-thumb {
  transform: translateX(12px);
  background: var(--white);
}

.toggle-text {
  font-size: 12px;
  line-height: 1;
}

/* ── §5 アカウントチップ ── */
/* プロバイダごとのグループ（Gmail: [..] [..]） */
.account-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.account-provider-name {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--ocean);
  min-width: 48px;
}

.account-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.account-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ocean);
  background: var(--mist);
  border: 1.5px solid var(--sage-weak);
  border-radius: var(--radius-pill);
  padding: 4px 12px;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out-expo),
              border-color var(--dur-fast) var(--ease-out-expo),
              transform 100ms var(--ease-spring);
}
.account-chip:hover:not(.account-chip--active) {
  background: var(--ocean-08);
  border-color: var(--ocean-20);
}
.account-chip:active {
  transform: scale(0.95);
}
.account-chip--active {
  background: var(--ocean);
  color: var(--white);
  border-color: var(--ocean);
  font-weight: 700;
}

/* chip-x（共通） */
.chip-x {
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  opacity: 0.75;
}
</style>
