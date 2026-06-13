<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ importance: number }>();

const level = computed(() => Math.min(5, Math.max(1, props.importance)));
const label = computed(() => `重要度 ${level.value} / 5`);
</script>

<template>
  <span
    class="blob num"
    :class="`imp-${level}`"
    :title="label"
    :aria-label="label"
  >
    {{ level }}
  </span>
</template>

<style scoped>
/* マーカーのインクだまり（ブロブ）．色＝重要度ランプにのみ予約 */
.blob {
  width: 30px;
  height: 30px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-blob);
  font-size: var(--text-14);
  font-weight: 700;
  color: var(--ink);
}
.imp-1 {
  background: var(--fl-cyan);
}
.imp-2 {
  background: var(--fl-green);
}
.imp-3 {
  background: var(--fl-yellow);
}
.imp-4 {
  background: var(--fl-orange);
}
.imp-5 {
  background: var(--fl-magenta);
  color: #fff;
}
</style>
