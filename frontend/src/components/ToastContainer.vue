<script setup lang="ts">
import { useToast } from "../composables/useToast";

const { toasts, dismiss } = useToast();

const ICONS: Record<string, string> = {
  info: "M12 8h.01M12 12v4",
  success: "M9 12l2 2 4-4",
  error: "M12 8v4m0 4h.01",
  warn: "M12 8v4m0 4h.01",
};
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite" aria-atomic="false">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="toast"
          :class="`toast--${t.type}`"
          role="status"
        >
          <div class="toast-body">
            <svg class="toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/>
              <path :d="ICONS[t.type]"/>
            </svg>
            <span class="toast-msg">{{ t.message }}</span>
            <button
              v-if="t.action"
              type="button"
              class="toast-action"
              @click="t.action.fn(); dismiss(t.id)"
            >{{ t.action.label }}</button>
            <button
              type="button"
              class="toast-close"
              aria-label="閉じる"
              @click="dismiss(t.id)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
          <div
            v-if="t.duration > 0"
            class="toast-progress"
            :style="{ animationDuration: `${t.duration}ms` }"
          />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 24px;
  left: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

/* ── ガラス化トースト ── */
.toast {
  pointer-events: all;
  display: flex;
  flex-direction: column;
  /* .glass はグローバルに定義済み．scoped 内で上書き・補完する */
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  min-width: 260px;
  max-width: 380px;
  overflow: hidden;
  will-change: transform, opacity;
  /* glass ユーティリティの値を直接展開（グローバル .glass は scoped に届かないため） */
  background: var(--glass-bg);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
  box-shadow: var(--glass-highlight), var(--glass-hairline), var(--glass-shadow);
  isolation: isolate;
  position: relative;
}

/* 鏡面ハイライト（::after は ::before と干渉しないよう before に振る） */
.toast::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(to bottom, rgba(255,255,255,0.40) 0%, rgba(255,255,255,0.06) 22%, transparent 50%);
  pointer-events: none;
  z-index: 0;
}
.toast > * { position: relative; z-index: 1; }

.toast-body {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px 11px 12px;
}

/*
 * 種別色はガラス地 + 左枠（border-left）＋アイコン色で示す．
 * 文字は常に ocean．ガラス面は明サーフェスなので ocean が読める．
 */

/* info: ocean 左枠 1px + ocean アイコン */
.toast--info {
  border-left: 3px solid var(--ocean);
  color: var(--ocean);
}
/* success: leaf 左枠 + leaf アイコン（文字は ocean） */
.toast--success {
  border-left: 3px solid var(--leaf);
  color: var(--ocean);
}
/* warn: sand 左枠 + sand アイコン（文字は ocean） */
.toast--warn {
  border-left: 3px solid var(--sand);
  color: var(--ocean);
}
/* error: ocean 太枠 2px + ocean 文字 + weight600（赤なし） */
.toast--error {
  border-left: 5px solid var(--ocean);
  color: var(--ocean);
  font-weight: 600;
}

/* アイコン色を種別ごとに調整（文字 currentColor から切り離す） */
.toast--info    .toast-icon { color: var(--ocean); }
.toast--success .toast-icon { color: var(--leaf); }
.toast--warn    .toast-icon { color: var(--sand); }
.toast--error   .toast-icon { color: var(--ocean); }

.toast-icon { flex-shrink: 0; }

.toast-msg {
  flex: 1;
  line-height: 1.45;
  color: var(--ocean);
}

.toast-action {
  background: none;
  border: none;
  padding: 0;
  font-size: inherit;
  font-weight: 600;
  cursor: pointer;
  color: var(--ocean);
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
}
.toast-close {
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: var(--ocean);
  opacity: 0.5;
  display: flex;
  align-items: center;
  border-radius: 50%;
  transition: opacity var(--dur-fast) var(--ease-standard),
              background var(--dur-fast) var(--ease-standard);
}
.toast-close:hover {
  opacity: 1;
  background: var(--ocean-12);
}

/* Progress bar: ocean 固定（種別を問わず ocean で統一・薄くならないように） */
.toast-progress {
  height: 3px;
  background: var(--ocean);
  opacity: 0.5;
  transform-origin: left;
  animation: toast-shrink linear forwards;
}

@keyframes toast-shrink {
  from { transform: scaleX(1); }
  to   { transform: scaleX(0); }
}

/*
 * 出入りアニメーション
 * 入場: 下から spring（弾む）
 * 退場: 下へ滑らか（--ease-out-expo を逆用）
 * easing は styles.css 定義のトークンに従う
 */
.toast-enter-active {
  transition:
    transform var(--dur-base) var(--ease-spring),
    opacity 200ms var(--ease-standard);
}
.toast-leave-active {
  transition:
    transform var(--dur-base) var(--ease-out-expo),
    opacity var(--dur-base) var(--ease-out-expo);
}
.toast-move {
  transition: transform var(--dur-base) var(--ease-out-expo);
}
.toast-enter-from {
  transform: translateY(110%) scale(0.95);
  opacity: 0;
}
.toast-leave-to {
  transform: translateY(110%) scale(0.95);
  opacity: 0;
}
.toast-leave-active {
  position: absolute;
}
</style>
