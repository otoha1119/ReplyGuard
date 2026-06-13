<script setup lang="ts">
import { computed } from "vue";
import type { MessageState } from "../types";

const props = defineProps<{ state: MessageState }>();

const LABELS: Record<MessageState, string> = {
  unhandled: "未対応",
  in_progress: "対応中",
  done: "完了",
  snoozed: "保留",
  dismissed: "対象外",
};

const label = computed(() => LABELS[props.state]);
</script>

<template>
  <span class="state" :class="`state-${state}`">
    <span v-if="state !== 'unhandled'" class="hue-dot" aria-hidden="true" />
    {{ label }}
  </span>
</template>

<style scoped>
/* 柔らかい pill チップ: 文字は常にインク（AA 安定），色相は前置ドットで示す */
.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px var(--space-3);
  border-radius: var(--radius-pill);
  font-size: var(--text-12);
  font-weight: 700;
  color: var(--ink);
}
.hue-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
/* 未対応だけ反転の最強表現 */
.state-unhandled {
  background: var(--ink);
  color: #fff;
}
.state-in_progress {
  background: var(--fl-cyan-tint);
}
.state-in_progress .hue-dot {
  background: var(--fl-cyan);
}
.state-done {
  background: var(--fl-green-tint);
}
.state-done .hue-dot {
  background: var(--fl-green);
}
.state-snoozed {
  background: var(--fl-yellow-tint);
}
.state-snoozed .hue-dot {
  background: color-mix(in srgb, var(--fl-yellow) 80%, var(--ink));
}
.state-dismissed {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--line);
  color: var(--ink-faint);
}
.state-dismissed .hue-dot {
  background: var(--line);
}
</style>
