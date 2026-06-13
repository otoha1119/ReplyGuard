<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ importance: number }>();

const level = computed(() => Math.min(6, Math.max(1, props.importance)));
const label = computed(() => `重要度 ${level.value} / 6`);

// Dot positions for each die face (cx, cy pairs within 0 0 20 20 viewBox)
const DOTS: Record<number, [number, number][]> = {
  1: [[10, 10]],
  2: [[6, 6], [14, 14]],
  3: [[6, 6], [10, 10], [14, 14]],
  4: [[6, 6], [14, 6], [6, 14], [14, 14]],
  5: [[6, 6], [14, 6], [10, 10], [6, 14], [14, 14]],
  6: [[6, 5], [6, 10], [6, 15], [14, 5], [14, 10], [14, 15]],
};
</script>

<template>
  <span
    class="imp"
    :class="`imp-${level}`"
    :title="label"
    :aria-label="label"
  >
    <svg width="44" height="44" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="0.8" y="0.8" width="18.4" height="18.4" rx="4" fill="currentColor" opacity="0.16" stroke="currentColor" stroke-width="1.5"/>
      <circle
        v-for="([cx, cy], i) in DOTS[level]"
        :key="i"
        :cx="cx"
        :cy="cy"
        r="1.9"
        fill="currentColor"
      />
    </svg>
  </span>
</template>

<style scoped>
/*
 * ImportanceBadge — サイコロの目（1〜5ピップ）で重要度を示す
 * 色は --imp-1..5（styles.css 定義）：sage→ocean50→ocean72→ocean→ocean
 * レベル5のみ sand の暈し（halo glow）で「最高・温かく際立つ」を表現
 * レベル4・5は hover 時に「転がり」回転（±8deg, 380ms, 弾みeasing）
 * prefers-reduced-motion で全アニメーション停止（styles.css の大域 rule で担保）
 * DESIGN.md §1 §6 準拠．
 */

.imp {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

/* 重要度色（currentColor を SVG が参照）：低=鼠 / 中=緑 / 高=青 */
.imp-1 { color: var(--imp-1); }
.imp-2 { color: var(--imp-2); }
.imp-3 { color: var(--imp-3); }
.imp-4 { color: var(--imp-4); }
.imp-5 { color: var(--imp-5); }
.imp-6 { color: var(--imp-6); }

/* レベル4以上: hover でふわっと拡大（弾みeasing） */
.imp-4,
.imp-5,
.imp-6 {
  transition: transform var(--dur-base) var(--ease-spring);
}
.imp-4:hover,
.imp-5:hover,
.imp-6:hover {
  transform: scale(1.18);
}

/* レベル5・6: sand の暈し（halo）で最重要を温かく際立たせる */
.imp-5,
.imp-6 {
  filter: drop-shadow(0 0 6px var(--sand));
}
</style>
