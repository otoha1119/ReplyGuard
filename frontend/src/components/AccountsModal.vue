<script setup lang="ts">
import { ref, onMounted } from "vue";
import type { AccountConfig, AccountConfigCreate } from "../types";
import { getAccounts, createAccount, deleteAccount } from "../api";

const emit = defineEmits<{
  "accounts-changed": [];
  close: [];
}>();

// --- 登録済みアカウント ---
const accounts = ref<AccountConfig[]>([]);
const listLoading = ref(false);
const listError = ref<string | null>(null);

async function loadAccounts(): Promise<void> {
  listLoading.value = true;
  listError.value = null;
  try {
    accounts.value = await getAccounts();
  } catch (e) {
    listError.value = e instanceof Error ? e.message : "取得に失敗しました.";
  } finally {
    listLoading.value = false;
  }
}

const deletingId = ref<string | null>(null);
const deleteError = ref<string | null>(null);

async function onDelete(id: string): Promise<void> {
  deletingId.value = id;
  deleteError.value = null;
  try {
    await deleteAccount(id);
    await loadAccounts();
    emit("accounts-changed");
  } catch (e) {
    deleteError.value = e instanceof Error ? e.message : "削除に失敗しました.";
  } finally {
    deletingId.value = null;
  }
}

// --- 追加フォーム ---
const selectedProvider = ref("gmail");
const form = ref<AccountConfigCreate>({
  provider: "gmail",
  label: "",
  address: "",
  credential: "",
});
const formError = ref<string | null>(null);
const submitting = ref(false);

function onAddressInput(): void {
  // address 入力時に label が未編集なら自動セット
  if (!labelEdited.value) {
    form.value.label = form.value.address;
  }
}

const labelEdited = ref(false);
function onLabelInput(): void {
  labelEdited.value = form.value.label !== form.value.address;
}

function selectProvider(p: string): void {
  selectedProvider.value = p;
  form.value.provider = p;
}

async function onSubmit(): Promise<void> {
  formError.value = null;
  if (!form.value.label.trim()) {
    formError.value = "表示名を入力してください.";
    return;
  }
  if (!form.value.address.trim()) {
    formError.value = "メールアドレスを入力してください.";
    return;
  }
  if (!form.value.credential.trim()) {
    formError.value = "アプリパスワードを入力してください.";
    return;
  }
  submitting.value = true;
  try {
    await createAccount({ ...form.value });
    // フォームリセット
    form.value = { provider: selectedProvider.value, label: "", address: "", credential: "" };
    labelEdited.value = false;
    await loadAccounts();
    emit("accounts-changed");
  } catch (e) {
    formError.value = e instanceof Error ? e.message : "追加に失敗しました.";
  } finally {
    submitting.value = false;
  }
}

function onOverlayClick(e: MouseEvent): void {
  if ((e.target as HTMLElement).classList.contains("modal-overlay")) {
    emit("close");
  }
}

onMounted(() => {
  void loadAccounts();
});
</script>

<template>
  <div class="modal-overlay" role="dialog" aria-modal="true" aria-label="アカウント設定" @click="onOverlayClick">
    <div class="modal-card">
      <!-- ヘッダー -->
      <div class="modal-header">
        <span class="modal-title">アカウント設定</span>
        <button type="button" class="close-btn" aria-label="閉じる" @click="emit('close')">✕</button>
      </div>

      <!-- 登録済みアカウント -->
      <section class="section">
        <h2 class="section-title">登録済みアカウント</h2>
        <p v-if="listError" class="banner err" role="alert">{{ listError }}</p>
        <p v-if="deleteError" class="banner err" role="alert">{{ deleteError }}</p>
        <p v-if="listLoading" class="muted-msg">読み込み中…</p>
        <p v-else-if="accounts.length === 0" class="muted-msg">まだ登録されていません.</p>
        <ul v-else class="account-list">
          <li v-for="ac in accounts" :key="ac.id" class="account-item">
            <span class="account-provider">{{ ac.provider }}</span>
            <span class="account-label">{{ ac.label }}</span>
            <button
              type="button"
              class="btn-danger-sm"
              :disabled="deletingId === ac.id"
              @click="onDelete(ac.id)"
            >
              {{ deletingId === ac.id ? "削除中…" : "削除" }}
            </button>
          </li>
        </ul>
      </section>

      <hr class="divider" />

      <!-- 追加フォーム -->
      <section class="section">
        <h2 class="section-title">アカウントを追加</h2>

        <!-- プロバイダ選択 -->
        <div class="provider-row">
          <button
            type="button"
            class="provider-btn"
            :class="{ active: selectedProvider === 'gmail' }"
            @click="selectProvider('gmail')"
          >
            Gmail
          </button>
          <button type="button" class="provider-btn" disabled>
            Slack
            <span class="soon-badge">近日公開</span>
          </button>
          <button type="button" class="provider-btn" disabled>
            Outlook
            <span class="soon-badge">近日公開</span>
          </button>
        </div>

        <!-- フォーム -->
        <p v-if="formError" class="banner err" role="alert">{{ formError }}</p>
        <form class="form" @submit.prevent="onSubmit">
          <div class="field">
            <label class="label" for="account-label">表示名</label>
            <input
              id="account-label"
              v-model="form.label"
              type="text"
              class="input"
              placeholder="例: 仕事用 Gmail"
              autocomplete="off"
              @input="onLabelInput"
            />
          </div>
          <div class="field">
            <label class="label" for="account-address">メールアドレス</label>
            <input
              id="account-address"
              v-model="form.address"
              type="email"
              class="input"
              placeholder="you@gmail.com"
              autocomplete="email"
              @input="onAddressInput"
            />
          </div>
          <div class="field">
            <label class="label" for="account-credential">アプリパスワード</label>
            <input
              id="account-credential"
              v-model="form.credential"
              type="password"
              class="input"
              placeholder="Google アプリパスワード（16桁）"
              autocomplete="new-password"
            />
          </div>
          <div class="form-footer">
            <button type="submit" class="btn-primary" :disabled="submitting">
              {{ submitting ? "追加中…" : "追加する" }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(35, 32, 56, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-card {
  background: var(--card);
  border-radius: var(--radius-panel);
  width: 480px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  box-shadow: var(--elev-3);
  color: var(--ink);
  animation: modal-pop var(--duration-base) var(--ease-spring) both;
}
@keyframes modal-pop {
  from {
    opacity: 0;
    transform: scale(0.94) translateY(12px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-6);
  border-bottom: 1.5px solid var(--line);
  position: sticky;
  top: 0;
  background: var(--card);
  z-index: 1;
}

.modal-title {
  font-size: var(--text-16);
  font-weight: 700;
  color: var(--ink);
}

.close-btn {
  background: none;
  border: none;
  font-size: var(--text-16);
  color: var(--ink-soft);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-pill);
  line-height: 1;
  cursor: pointer;
}
.close-btn:hover {
  background: var(--card-inset);
  color: var(--ink);
}

.section {
  padding: var(--space-4) var(--space-6);
}

.section-title {
  font-size: var(--text-12);
  font-weight: 700;
  color: var(--ink-soft);
  margin: 0 0 var(--space-3);
}

.divider {
  border: none;
  border-top: 1.5px solid var(--line);
  margin: 0;
}

/* アカウント一覧 */
.account-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.account-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--card-inset);
  border-radius: var(--radius-pill);
}

.account-provider {
  font-size: var(--text-12);
  font-weight: 700;
  color: var(--ink);
  background: var(--fl-cyan-tint);
  border-radius: var(--radius-pill);
  padding: 1px var(--space-3);
  white-space: nowrap;
}

.account-label {
  flex: 1;
  font-size: var(--text-12);
  color: var(--ink);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-danger-sm {
  font-size: var(--text-12);
  padding: 2px var(--space-3);
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--rose);
  background: transparent;
  color: var(--rose);
  white-space: nowrap;
  cursor: pointer;
}
.btn-danger-sm:hover:not(:disabled) {
  background: var(--rose-tint);
}
.btn-danger-sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* プロバイダ選択 */
.provider-row {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.provider-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-12);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--line);
  background: var(--card);
  color: var(--ink);
  cursor: pointer;
  transition: border-color var(--duration-micro) var(--ease-smooth),
    background var(--duration-micro) var(--ease-smooth);
}
.provider-btn.active {
  border-color: var(--fl-cyan);
  background: var(--fl-cyan-tint);
  color: var(--ink);
  font-weight: 700;
}
.provider-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.soon-badge {
  font-size: var(--text-12);
  padding: 0 var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--card-inset);
  color: var(--ink-faint);
  white-space: nowrap;
}

/* フォーム */
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.label {
  font-size: var(--text-12);
  font-weight: 700;
  color: var(--ink-soft);
}

.input {
  font: inherit;
  font-size: var(--text-14);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-pill);
  border: 1.5px solid var(--line);
  background: var(--card);
  color: var(--ink);
  outline: none;
  transition: border-color var(--duration-micro) var(--ease-smooth);
}
.input:focus {
  border-color: var(--fl-cyan);
}

.form-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-1);
}

.btn-primary {
  font-size: var(--text-14);
  font-weight: 700;
  padding: var(--space-2) var(--space-6);
  border-radius: var(--radius-pill);
  border: none;
  background: var(--ink);
  color: #fff;
  cursor: pointer;
  transition: transform var(--duration-micro) var(--ease-spring),
    box-shadow var(--duration-micro) var(--ease-spring);
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--elev-2);
}
.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* バナー・メッセージ */
.banner {
  margin: 0 0 var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-inset);
  font-size: var(--text-12);
}
.banner.err {
  color: var(--ink);
  background: var(--rose-tint);
}

.muted-msg {
  font-size: var(--text-12);
  color: var(--ink-soft);
  margin: 0;
  padding: var(--space-2) 0;
}
</style>
