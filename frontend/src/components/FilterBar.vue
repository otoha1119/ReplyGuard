<script setup lang="ts">
import { computed, ref } from "vue";
import type { MessagesQuery } from "../api";
import type { AccountConfig } from "../types";

const props = defineProps<{
  modelValue: MessagesQuery;
  providers: string[];
  accounts: AccountConfig[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: MessagesQuery];
}>();

const expanded = ref(false);

function patch(updates: Partial<MessagesQuery>): void {
  emit("update:modelValue", { ...props.modelValue, ...updates });
}

// --- Sort ---
const ORDER_BY_OPTIONS: Array<{ value: NonNullable<MessagesQuery["order_by"]>; label: string }> = [
  { value: "triage_score", label: "推奨度" },
  { value: "received_at", label: "受信日時" },
  { value: "importance", label: "重要度" },
];

function setOrderBy(e: Event): void {
  patch({ order_by: (e.target as HTMLSelectElement).value as MessagesQuery["order_by"] });
}

function toggleDescending(): void {
  patch({ descending: !(props.modelValue.descending ?? true) });
}

// --- Providers ---
// undefined = フィルターなし（全選択と同等）, [] = 明示的に全解除（0件）
function isChecked(p: string): boolean {
  const ps = props.modelValue.providers;
  if (ps === undefined) return true;
  return ps.includes(p);
}

function toggleProvider(p: string): void {
  const current = props.modelValue.providers;
  const all = props.providers;
  if (current === undefined) {
    // 未設定（全表示）→ 1つ外す → 他を明示選択
    const next = all.filter((x) => x !== p);
    patch({ providers: next });
  } else if (current.includes(p)) {
    const next = current.filter((x) => x !== p);
    // 全部外れたら [] = 明示的に何も表示しない（undefined にしない）
    patch({ providers: next });
  } else {
    const next = [...current, p];
    // 全プロバイダが揃ったら undefined（= フィルターなし）に戻す
    patch({ providers: next.length >= all.length ? undefined : next });
  }
}

// --- Importance ---
const IMPORTANCE_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: "すべて" },
  { value: 1, label: "1以上" },
  { value: 2, label: "2以上" },
  { value: 3, label: "3以上" },
  { value: 4, label: "4以上" },
  { value: 5, label: "5のみ" },
];

function setImportanceMin(e: Event): void {
  const n = Number((e.target as HTMLSelectElement).value);
  patch({ importance_min: n > 0 ? n : undefined });
}

// --- Dates ---
function toDateInput(iso: string | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

function setReceivedAfter(e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  patch({ received_after: v ? `${v}T00:00:00Z` : undefined });
}

function setReceivedBefore(e: Event): void {
  const v = (e.target as HTMLInputElement).value;
  patch({ received_before: v ? `${v}T23:59:59Z` : undefined });
}

// --- Unread only ---
function setUnreadOnly(e: Event): void {
  const checked = (e.target as HTMLInputElement).checked;
  patch({ unread_only: checked || undefined });
}

// --- Accounts ---
function isAccountChecked(address: string): boolean {
  const as = props.modelValue.account_addresses;
  if (as === undefined) return true;
  return as.includes(address);
}

function toggleAccount(address: string): void {
  const current = props.modelValue.account_addresses;
  const allAddresses = props.accounts.map((a) => a.address);
  if (current === undefined) {
    const next = allAddresses.filter((x) => x !== address);
    patch({ account_addresses: next });
  } else if (current.includes(address)) {
    const next = current.filter((x) => x !== address);
    patch({ account_addresses: next });
  } else {
    const next = [...current, address];
    patch({ account_addresses: next.length >= allAddresses.length ? undefined : next });
  }
}

// --- Active filter count (sort 除く) ---
const activeFilterCount = computed<number>(() => {
  let n = 0;
  const q = props.modelValue;
  if (q.providers !== undefined) n++;
  if (q.account_addresses !== undefined) n++;
  if (q.importance_min && q.importance_min > 0) n++;
  if (q.received_after) n++;
  if (q.received_before) n++;
  if (q.unread_only) n++;
  return n;
});

function clearFilters(): void {
  emit("update:modelValue", {
    archived: props.modelValue.archived,
    order_by: props.modelValue.order_by,
    descending: props.modelValue.descending,
  });
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s.charAt(0).toUpperCase() + s.slice(1);
}
</script>

<template>
  <div class="filter-bar">
    <!-- ソートコントロール（常時表示） -->
    <div class="sort-row">
      <div class="sort-controls">
        <label class="ctrl-label" for="sort-select">並べ替え</label>
        <select
          id="sort-select"
          class="ctrl-select"
          :value="modelValue.order_by ?? 'triage_score'"
          @change="setOrderBy"
        >
          <option
            v-for="opt in ORDER_BY_OPTIONS"
            :key="opt.value"
            :value="opt.value"
          >{{ opt.label }}</option>
        </select>
        <button
          type="button"
          class="dir-btn"
          :aria-label="(modelValue.descending ?? true) ? '降順（クリックで昇順に変更）' : '昇順（クリックで降順に変更）'"
          @click="toggleDescending"
        >
          {{ (modelValue.descending ?? true) ? "↓" : "↑" }}
        </button>
      </div>
      <button
        type="button"
        class="filter-toggle-btn"
        :aria-expanded="expanded ? 'true' : 'false'"
        @click="expanded = !expanded"
      >
        フィルター
        <span
          v-if="activeFilterCount > 0"
          class="filter-badge"
          :aria-label="`${activeFilterCount}件のフィルター適用中`"
        >{{ activeFilterCount }}</span>
      </button>
    </div>

    <!-- フィルターパネル（折りたたみ） -->
    <Transition name="pop">
    <div
      v-if="expanded"
      class="filter-panel"
      role="group"
      aria-label="フィルター条件"
    >
      <!-- プロバイダ -->
      <div v-if="providers.length > 0" class="filter-group">
        <span class="group-label">アプリ</span>
        <div class="checkbox-row">
          <label
            v-for="p in providers"
            :key="p"
            class="check-item"
          >
            <input
              type="checkbox"
              :checked="isChecked(p)"
              @change="toggleProvider(p)"
            />
            {{ capitalize(p) }}
          </label>
        </div>
      </div>

      <!-- アカウント -->
      <div v-if="accounts.length > 0" class="filter-group">
        <span class="group-label">アカウント</span>
        <div class="checkbox-row">
          <label
            v-for="ac in accounts"
            :key="ac.id"
            class="check-item"
          >
            <input
              type="checkbox"
              :checked="isAccountChecked(ac.address)"
              @change="toggleAccount(ac.address)"
            />
            {{ ac.label }}
          </label>
        </div>
      </div>

      <!-- 重要度 -->
      <div class="filter-group">
        <label class="group-label" for="importance-select">重要度（最低）</label>
        <select
          id="importance-select"
          class="ctrl-select"
          :value="modelValue.importance_min ?? 0"
          @change="setImportanceMin"
        >
          <option
            v-for="opt in IMPORTANCE_OPTIONS"
            :key="opt.value"
            :value="opt.value"
          >{{ opt.label }}</option>
        </select>
      </div>

      <!-- 受信日時（from / to） -->
      <div class="filter-group">
        <span class="group-label">受信日時</span>
        <div class="date-range">
          <input
            type="date"
            class="date-input"
            aria-label="受信日時（from）"
            :value="toDateInput(modelValue.received_after)"
            @change="setReceivedAfter"
          />
          <span class="date-sep" aria-hidden="true">〜</span>
          <input
            type="date"
            class="date-input"
            aria-label="受信日時（to）"
            :value="toDateInput(modelValue.received_before)"
            @change="setReceivedBefore"
          />
        </div>
      </div>

      <!-- 未読のみ -->
      <div class="filter-group">
        <label class="check-item">
          <input
            type="checkbox"
            :checked="modelValue.unread_only ?? false"
            @change="setUnreadOnly"
          />
          未読のみ
        </label>
      </div>

      <!-- クリア -->
      <div class="filter-actions">
        <button
          type="button"
          class="clear-btn"
          :disabled="activeFilterCount === 0"
          @click="clearFilters"
        >
          フィルタークリア
        </button>
      </div>
    </div>
    </Transition>
  </div>
</template>

<style scoped>
.filter-bar {
  margin-bottom: var(--space-4);
}

.sort-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.sort-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
}

.ctrl-label,
.group-label {
  font-size: var(--text-12);
  color: var(--ink-soft);
  white-space: nowrap;
}

.ctrl-select {
  font-size: var(--text-12);
  padding: var(--space-1) var(--space-3);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--ink);
}

.dir-btn {
  font-size: var(--text-14);
  width: 32px;
  height: 32px;
  border: 1.5px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--ink-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth);
}

.dir-btn:hover {
  background: var(--card-inset);
  color: var(--ink);
}

.filter-toggle-btn {
  font-size: var(--text-12);
  font-weight: 500;
  padding: var(--space-1) var(--space-4);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--ink-soft);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth);
}

.filter-toggle-btn:hover {
  background: var(--card-inset);
  color: var(--ink);
}

.filter-badge {
  font-size: var(--text-12);
  font-weight: 700;
  background: var(--ink);
  color: #fff;
  border-radius: var(--radius-pill);
  padding: 0 var(--space-2);
  min-width: 18px;
  text-align: center;
}

.filter-panel {
  margin-top: var(--space-3);
  padding: var(--space-4) var(--space-6);
  background: var(--card);
  border-radius: var(--radius-card);
  box-shadow: var(--elev-1);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-6);
  align-items: flex-start;
  transform-origin: top left;
}

/* パネルの弾む出現 */
.pop-enter-active {
  transition: opacity var(--duration-micro) var(--ease-spring),
    transform var(--duration-micro) var(--ease-spring);
}
.pop-leave-active {
  transition: opacity var(--duration-micro) var(--ease-smooth),
    transform var(--duration-micro) var(--ease-smooth);
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(-6px);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.checkbox-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
}

.check-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-12);
  color: var(--ink);
  cursor: pointer;
  user-select: none;
}

.check-item input[type="checkbox"] {
  accent-color: var(--fl-cyan);
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.date-range {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.date-input {
  font-size: var(--text-12);
  padding: var(--space-1) var(--space-3);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--card);
  color: var(--ink);
}

.date-sep {
  color: var(--ink-soft);
  font-size: var(--text-12);
}

.filter-actions {
  margin-left: auto;
  display: flex;
  align-items: flex-end;
}

.clear-btn {
  font-size: var(--text-12);
  padding: var(--space-1) var(--space-4);
  border: 1.5px solid var(--line);
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--ink-soft);
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth),
    border-color var(--duration-micro) var(--ease-smooth);
}

.clear-btn:hover:not(:disabled) {
  color: var(--rose);
  border-color: var(--rose);
  background: var(--rose-tint);
}

.clear-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
