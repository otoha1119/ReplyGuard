<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { MessageRecord, MessageState } from "./types";
import {
  type MessagesQuery,
  ConflictError,
  getMessages,
  getProviders,
  triggerIngest,
  unarchiveMessage,
  updateMessageState,
  getAccounts,
} from "./api";
import MessageCard from "./components/MessageCard.vue";
import FilterBar from "./components/FilterBar.vue";
import AccountsModal from "./components/AccountsModal.vue";

type Tab = "inbox" | "archive";

const records = ref<MessageRecord[]>([]);
const loading = ref(false);
const ingesting = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const busyIds = ref<Set<string>>(new Set());
const activeTab = ref<Tab>("inbox");
const availableProviders = ref<string[]>([]);

const inboxQuery = ref<MessagesQuery>({
  archived: false,
  order_by: "importance",
  descending: true,
});
const archiveQuery = ref<MessagesQuery>({
  archived: true,
  order_by: "importance",
  descending: true,
});

const unhandledCount = computed(
  () => records.value.filter((r) => r.state === "unhandled").length,
);
const needsReplyCount = computed(
  () => records.value.filter((r) => r.analysis?.needs_reply).length,
);
const inProgressCount = computed(
  () => records.value.filter((r) => r.state === "in_progress").length,
);
const snoozedCount = computed(
  () => records.value.filter((r) => r.state === "snoozed").length,
);

// Signature: 未対応 × 重要度4以上だけが「いま見るべき」ゾーンへ（受信トレイのみ）
const priorityRecords = computed(() =>
  activeTab.value === "inbox"
    ? records.value.filter(
        (r) => r.state === "unhandled" && (r.analysis?.importance ?? 1) >= 4,
      )
    : [],
);
const standardRecords = computed(() => {
  if (priorityRecords.value.length === 0) return records.value;
  const ids = new Set(priorityRecords.value.map((r) => r.message_id));
  return records.value.filter((r) => !ids.has(r.message_id));
});

// --- ヒーロー数字の count-up（JS アニメーション） ---
const reducedMotion =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const displayCount = ref(0);
let countRaf: number | null = null;

function animateCount(target: number): void {
  if (reducedMotion) {
    displayCount.value = target;
    return;
  }
  if (countRaf !== null) cancelAnimationFrame(countRaf);
  const start = displayCount.value;
  const t0 = performance.now();
  const duration = 700;
  const tick = (t: number): void => {
    const p = Math.min(1, (t - t0) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    displayCount.value = Math.round(start + (target - start) * eased);
    countRaf = p < 1 ? requestAnimationFrame(tick) : null;
  };
  countRaf = requestAnimationFrame(tick);
}

watch(unhandledCount, (n) => animateCount(n));

const tickerText = computed(
  () =>
    `REPLYGUARD ✦ INBOX STUDIO ✦ 未対応 ${unhandledCount.value} ✦ 要返信 ${needsReplyCount.value} ✦ 対応漏れゼロへ ✦ `,
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const query = activeTab.value === "inbox" ? inboxQuery.value : archiveQuery.value;
    records.value = await getMessages(query);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "読み込みに失敗しました.";
  } finally {
    loading.value = false;
  }
}

function onQueryChange(q: MessagesQuery): void {
  if (activeTab.value === "inbox") {
    inboxQuery.value = q;
  } else {
    archiveQuery.value = q;
  }
  void load();
}

async function switchTab(tab: Tab): Promise<void> {
  if (activeTab.value === tab) return;
  activeTab.value = tab;
  records.value = [];
  await load();
}

async function onIngest(): Promise<void> {
  ingesting.value = true;
  error.value = null;
  notice.value = null;
  try {
    await triggerIngest();
    await load();
    notice.value = "取り込みが完了しました.";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "取り込みに失敗しました.";
  } finally {
    ingesting.value = false;
  }
}

function setBusy(id: string, on: boolean): void {
  const next = new Set(busyIds.value);
  if (on) next.add(id);
  else next.delete(id);
  busyIds.value = next;
}

async function onChangeState(
  record: MessageRecord,
  state: MessageState,
): Promise<void> {
  setBusy(record.message_id, true);
  error.value = null;
  notice.value = null;
  try {
    await updateMessageState(record.message_id, state, record.version);
    // done/dismissed 後にバックエンドが自動アーカイブするため全件リフェッチ
    await load();
  } catch (e) {
    if (e instanceof ConflictError) {
      notice.value = e.message;
      await load();
    } else {
      error.value = e instanceof Error ? e.message : "更新に失敗しました.";
    }
  } finally {
    setBusy(record.message_id, false);
  }
}

async function onUnarchive(record: MessageRecord): Promise<void> {
  setBusy(record.message_id, true);
  error.value = null;
  notice.value = null;
  try {
    await unarchiveMessage(record.message_id);
    await load();
    notice.value = "受信トレイに復元しました.";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "復元に失敗しました.";
  } finally {
    setBusy(record.message_id, false);
  }
}

const AUTO_REFRESH_INTERVAL_MS = 60_000;
let autoRefreshTimer: ReturnType<typeof setInterval> | null = null;
const autoRefresh = ref(true);

function startAutoRefresh(): void {
  if (autoRefreshTimer !== null) return;
  autoRefreshTimer = setInterval(() => { void load(); }, AUTO_REFRESH_INTERVAL_MS);
}

function stopAutoRefresh(): void {
  if (autoRefreshTimer !== null) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

function toggleAutoRefresh(): void {
  autoRefresh.value = !autoRefresh.value;
  autoRefresh.value ? startAutoRefresh() : stopAutoRefresh();
}

// --- アカウント管理 ---
const showAccounts = ref(false);
const hasAccounts = ref<boolean | null>(null);
const accountsList = ref<import("./types").AccountConfig[]>([]);

async function refreshAccountStatus(): Promise<void> {
  try {
    const acs = await getAccounts();
    accountsList.value = acs;
    hasAccounts.value = acs.length > 0;
  } catch {
    // 取得失敗時は判定を null のまま（既存の空状態を表示しない）
    hasAccounts.value = null;
  }
}

function onAccountsChanged(): void {
  void refreshAccountStatus();
  void load();
}

function stagger(index: number): { transitionDelay: string } {
  return { transitionDelay: `${Math.min(index, 10) * 40}ms` };
}

onMounted(() => {
  void load();
  getProviders()
    .then((ps) => { availableProviders.value = ps; })
    .catch(() => {});
  void refreshAccountStatus();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
  if (countRaf !== null) cancelAnimationFrame(countRaf);
});
</script>

<template>
  <!-- 背景のドリフトするブロブ（ギャラリーの滲み） -->
  <div class="blobs" aria-hidden="true">
    <div class="blob b1" />
    <div class="blob b2" />
    <div class="blob b3" />
  </div>

  <!-- マーキーティッカー -->
  <div class="ticker" aria-hidden="true">
    <div class="ticker-track">
      <span class="ticker-text">{{ tickerText.repeat(3) }}</span>
      <span class="ticker-text">{{ tickerText.repeat(3) }}</span>
    </div>
  </div>

  <div class="studio">
    <header class="hero">
      <div class="hero-id">
        <h1 class="wordmark">Reply<em>Guard</em></h1>
        <p class="tagline">受信トレイ 仕分けスタジオ</p>
      </div>
      <div class="hero-actions">
        <button type="button" class="pill ghost" @click="showAccounts = true">
          アカウント
        </button>
        <button
          type="button"
          class="pill ghost"
          :class="{ on: autoRefresh }"
          :aria-pressed="autoRefresh ? 'true' : 'false'"
          @click="toggleAutoRefresh"
        >
          <span class="dot" aria-hidden="true" />
          自動更新
        </button>
        <button type="button" class="pill ghost" :disabled="loading" @click="load">
          再読込
        </button>
        <button
          type="button"
          class="pill primary"
          :disabled="loading || ingesting"
          @click="onIngest"
        >
          {{ ingesting ? "取り込み中…" : "取り込む" }}
        </button>
      </div>
    </header>

    <section class="counter-row">
      <div class="metric" :class="{ clear: unhandledCount === 0 }">
        <span class="metric-blob" aria-hidden="true" />
        <span class="metric-num num">{{ displayCount }}</span>
        <span class="metric-label">未対応</span>
      </div>
      <div class="stats" aria-label="現在の内訳">
        <span class="stat"><span class="stat-num num">{{ records.length }}</span>表示中</span>
        <span class="stat"><span class="stat-dot magenta" aria-hidden="true" /><span class="stat-num num">{{ needsReplyCount }}</span>要返信</span>
        <span class="stat"><span class="stat-dot cyan" aria-hidden="true" /><span class="stat-num num">{{ inProgressCount }}</span>対応中</span>
        <span class="stat"><span class="stat-dot yellow" aria-hidden="true" /><span class="stat-num num">{{ snoozedCount }}</span>保留</span>
      </div>
    </section>

    <nav class="tabs" role="tablist" aria-label="メールビュー切り替え">
      <button
        role="tab"
        :aria-selected="activeTab === 'inbox'"
        class="tab"
        :class="{ active: activeTab === 'inbox' }"
        @click="switchTab('inbox')"
      >
        受信トレイ
      </button>
      <button
        role="tab"
        :aria-selected="activeTab === 'archive'"
        class="tab"
        :class="{ active: activeTab === 'archive' }"
        @click="switchTab('archive')"
      >
        アーカイブ
      </button>
    </nav>

    <FilterBar
      :model-value="activeTab === 'inbox' ? inboxQuery : archiveQuery"
      :providers="availableProviders"
      :accounts="accountsList"
      @update:model-value="onQueryChange"
    />

    <p v-if="error" class="banner err" role="alert">{{ error }}</p>
    <p v-if="notice" class="banner info" role="status">{{ notice }}</p>

    <Transition name="view" mode="out-in">
      <div :key="activeTab" class="gallery">
        <div v-if="loading && records.length === 0" class="state-zone" role="status">
          <span class="loading-dots" aria-hidden="true">
            <span class="ld c" /><span class="ld y" /><span class="ld m" />
          </span>
          <span class="state-sub">読み込み中…</span>
        </div>

        <div
          v-else-if="!loading && records.length === 0 && !error && hasAccounts === false"
          class="state-zone"
        >
          <span class="state-blob" aria-hidden="true" />
          <span class="state-title">はじめましょう</span>
          <span class="state-sub">アカウントを追加すると，メッセージの取り込みが始まります.</span>
          <button type="button" class="pill primary" @click="showAccounts = true">
            アカウントを追加
          </button>
        </div>

        <div
          v-else-if="!loading && records.length === 0 && !error"
          class="state-zone"
        >
          <template v-if="activeTab === 'inbox'">
            <span class="state-blob green" aria-hidden="true" />
            <span class="state-title">ぜんぶ仕分け済み！</span>
            <span class="state-sub">新着が来たら「取り込む」でボードに並びます.</span>
          </template>
          <template v-else>
            <span class="state-blob" aria-hidden="true" />
            <span class="state-title">アーカイブは空です</span>
            <span class="state-sub">完了・対象外にしたメッセージがここに収まります.</span>
          </template>
        </div>

        <template v-else>
          <!-- Signature: いま見るべきゾーン -->
          <template v-if="priorityRecords.length > 0">
            <h2 class="zone-label">
              <span class="zone-blob" aria-hidden="true" />
              いま見るべき
              <span class="zone-count num">{{ priorityRecords.length }}</span>
            </h2>
            <TransitionGroup name="cards" tag="div" class="stack now-zone" appear>
              <div
                v-for="(r, i) in priorityRecords"
                :key="r.message_id"
                class="slot"
                :style="stagger(i)"
              >
                <MessageCard
                  :record="r"
                  :busy="busyIds.has(r.message_id)"
                  :mode="activeTab"
                  priority
                  @change-state="(s) => onChangeState(r, s)"
                  @unarchive="onUnarchive(r)"
                />
              </div>
            </TransitionGroup>
            <h2 class="zone-label rest">そのほか</h2>
          </template>

          <TransitionGroup name="cards" tag="div" class="stack" appear>
            <div
              v-for="(r, i) in standardRecords"
              :key="r.message_id"
              class="slot"
              :style="stagger(priorityRecords.length + i)"
            >
              <MessageCard
                :record="r"
                :busy="busyIds.has(r.message_id)"
                :mode="activeTab"
                @change-state="(s) => onChangeState(r, s)"
                @unarchive="onUnarchive(r)"
              />
            </div>
          </TransitionGroup>
        </template>
      </div>
    </Transition>

    <AccountsModal
      v-if="showAccounts"
      @close="showAccounts = false"
      @accounts-changed="onAccountsChanged"
    />
  </div>
</template>

<style scoped>
/* ============ 背景ブロブ ============ */
.blobs {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.blob {
  position: absolute;
  width: 480px;
  height: 480px;
  border-radius: var(--radius-blob);
  filter: blur(110px);
  opacity: 0.11;
  animation: drift 22s var(--ease-smooth) infinite alternate;
}
.b1 {
  background: var(--fl-cyan);
  top: -160px;
  left: -120px;
}
.b2 {
  background: var(--fl-magenta);
  top: 30%;
  right: -200px;
  animation-duration: 26s;
}
.b3 {
  background: var(--fl-yellow);
  bottom: -220px;
  left: 28%;
  animation-duration: 18s;
}
@keyframes drift {
  from {
    transform: translate(0, 0) rotate(0deg) scale(1);
  }
  to {
    transform: translate(60px, 40px) rotate(24deg) scale(1.12);
  }
}

/* ============ ティッカー ============ */
.ticker {
  position: relative;
  z-index: 1;
  background: var(--ink);
  color: #fff;
  overflow: hidden;
  white-space: nowrap;
}
.ticker-track {
  display: inline-flex;
  animation: marquee 40s linear infinite;
}
.ticker-text {
  font-family: var(--font-display);
  font-size: var(--text-12);
  font-weight: 500;
  letter-spacing: 0.12em;
  padding: var(--space-1) 0;
  text-transform: uppercase;
}
@keyframes marquee {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}

/* ============ スタジオ（メイン容器） ============ */
.studio {
  position: relative;
  z-index: 1;
  max-width: 880px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-6) var(--space-24);
}

/* ============ ヒーロー ============ */
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  flex-wrap: wrap;
}
.wordmark {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--text-28);
  font-weight: 900;
  color: var(--ink);
  line-height: 1.1;
}
.wordmark em {
  font-style: normal;
  color: var(--fl-magenta);
}
.tagline {
  margin: var(--space-1) 0 0;
  font-size: var(--text-12);
  color: var(--ink-soft);
}
.hero-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-12);
  font-weight: 500;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--line);
  background: var(--card);
  color: var(--ink-soft);
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth),
    transform var(--duration-micro) var(--ease-spring),
    box-shadow var(--duration-micro) var(--ease-spring);
}
.pill.ghost:hover:not(:disabled) {
  background: var(--card-inset);
  color: var(--ink);
}
.pill.primary {
  border: none;
  background: var(--ink);
  color: #fff;
  font-weight: 700;
}
.pill.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--elev-2);
}
.pill:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pill .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ink-faint);
  flex: none;
  transition: background var(--duration-micro) var(--ease-smooth);
}
.pill.on .dot {
  background: var(--fl-green);
}
.pill.on {
  color: var(--ink);
}

/* ============ ヒーロー数字＋内訳 ============ */
.counter-row {
  display: flex;
  align-items: center;
  gap: var(--space-8);
  margin: var(--space-8) 0 var(--space-6);
  flex-wrap: wrap;
}
.metric {
  position: relative;
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.metric-blob {
  position: absolute;
  left: -8px;
  top: -10px;
  width: 96px;
  height: 96px;
  background: var(--fl-magenta);
  border-radius: var(--radius-blob);
  opacity: 0.9;
  z-index: 0;
  transition: background var(--duration-base) var(--ease-smooth);
}
.metric.clear .metric-blob {
  background: var(--fl-green);
}
.metric-num {
  position: relative;
  z-index: 1;
  font-family: var(--font-display);
  font-size: var(--text-64);
  font-weight: 900;
  line-height: 1;
  color: var(--ink);
}
.metric-label {
  position: relative;
  z-index: 1;
  font-size: var(--text-14);
  font-weight: 700;
  color: var(--ink);
}
.stats {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.stat {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-12);
  color: var(--ink-soft);
  background: var(--card);
  border-radius: var(--radius-pill);
  box-shadow: var(--elev-1);
  padding: var(--space-1) var(--space-4);
}
.stat-num {
  font-family: var(--font-display);
  font-size: var(--text-14);
  font-weight: 700;
  color: var(--ink);
}
.stat-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.stat-dot.magenta {
  background: var(--fl-magenta);
}
.stat-dot.cyan {
  background: var(--fl-cyan);
}
.stat-dot.yellow {
  background: var(--fl-yellow);
}

/* ============ タブ ============ */
.tabs {
  display: inline-flex;
  gap: var(--space-1);
  background: var(--card-inset);
  border-radius: var(--radius-pill);
  padding: var(--space-1);
  margin-bottom: var(--space-4);
}
.tab {
  font-size: var(--text-14);
  font-weight: 500;
  padding: var(--space-2) var(--space-6);
  border-radius: var(--radius-pill);
  border: none;
  background: transparent;
  color: var(--ink-soft);
  transition: background var(--duration-micro) var(--ease-smooth),
    color var(--duration-micro) var(--ease-smooth);
}
.tab:hover {
  color: var(--ink);
}
.tab.active {
  background: var(--ink);
  color: #fff;
  font-weight: 700;
}

/* ============ バナー ============ */
.banner {
  margin: 0 0 var(--space-3);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-inset);
  font-size: var(--text-12);
  color: var(--ink);
}
.banner.err {
  background: var(--rose-tint);
}
.banner.info {
  background: var(--fl-cyan-tint);
}

/* ============ ギャラリー（カード一覧） ============ */
.gallery {
  min-height: 200px;
}
.stack {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.zone-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: var(--space-6) 0 var(--space-3);
  font-size: var(--text-16);
  font-weight: 700;
  color: var(--ink);
}
.zone-label:first-of-type {
  margin-top: var(--space-2);
}
.zone-blob {
  width: 18px;
  height: 18px;
  background: var(--fl-magenta);
  border-radius: var(--radius-blob);
  flex: none;
}
.zone-count {
  font-family: var(--font-display);
  font-size: var(--text-14);
  font-weight: 700;
  background: var(--fl-magenta-tint);
  border-radius: var(--radius-pill);
  padding: 0 var(--space-3);
}
.zone-label.rest {
  font-size: var(--text-14);
  color: var(--ink-soft);
}

/* いま見るべきゾーンはわずかに回転（現代アートの貼り紙） */
.now-zone .slot:nth-child(odd) {
  transform: rotate(-0.6deg);
}
.now-zone .slot:nth-child(even) {
  transform: rotate(0.5deg);
}

/* ============ カードの出現・移動・退場（FLIP） ============ */
.cards-enter-active {
  transition: opacity var(--duration-base) var(--ease-spring),
    transform var(--duration-base) var(--ease-spring);
}
.cards-leave-active {
  position: absolute;
  width: 100%;
  transition: opacity var(--duration-micro) var(--ease-smooth),
    transform var(--duration-micro) var(--ease-smooth);
}
.cards-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.97);
}
.cards-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
.cards-move {
  transition: transform var(--duration-base) var(--ease-smooth);
}

/* ============ タブ切替の画面遷移 ============ */
.view-enter-active,
.view-leave-active {
  transition: opacity var(--duration-micro) var(--ease-smooth),
    transform var(--duration-micro) var(--ease-smooth);
}
.view-enter-from {
  opacity: 0;
  transform: translateX(24px);
}
.view-leave-to {
  opacity: 0;
  transform: translateX(-24px);
}

/* ============ 空・読み込み状態 ============ */
.state-zone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-16) 0;
  text-align: center;
}
.state-blob {
  width: 72px;
  height: 72px;
  background: var(--fl-cyan);
  border-radius: var(--radius-blob);
  opacity: 0.85;
}
.state-blob.green {
  background: var(--fl-green);
}
.state-title {
  font-size: var(--text-20);
  font-weight: 700;
  color: var(--ink);
}
.state-sub {
  font-size: var(--text-12);
  color: var(--ink-soft);
}
.loading-dots {
  display: flex;
  gap: var(--space-2);
}
.ld {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  animation: bounce 900ms var(--ease-smooth) infinite alternate;
}
.ld.c {
  background: var(--fl-cyan);
}
.ld.y {
  background: var(--fl-yellow);
  animation-delay: 150ms;
}
.ld.m {
  background: var(--fl-magenta);
  animation-delay: 300ms;
}
@keyframes bounce {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(-10px);
  }
}

/* ============ レスポンシブ ============ */
@media (max-width: 720px) {
  .studio {
    padding: var(--space-4) var(--space-4) var(--space-16);
  }
  .counter-row {
    gap: var(--space-4);
    margin: var(--space-6) 0 var(--space-4);
  }
  .metric-num {
    font-size: var(--text-40);
  }
  .metric-blob {
    width: 64px;
    height: 64px;
    left: -4px;
    top: -6px;
  }
}
</style>
