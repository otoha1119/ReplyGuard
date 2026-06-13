import { onMounted, onUnmounted, type Ref } from "vue";

/**
 * 要素がビューポートに入ったら一度だけ `.revealed` を付与するスクロール reveal.
 * styles.css の `.reveal` / `.reveal.revealed` と対で使う.
 * prefers-reduced-motion 時は即座に表示する（IntersectionObserver を張らない）.
 */
export function useReveal(
  el: Ref<HTMLElement | null>,
  options: { threshold?: number; once?: boolean } = {},
): void {
  const { threshold = 0.15, once = true } = options;
  let observer: IntersectionObserver | null = null;

  onMounted(() => {
    const target = el.value;
    if (!target) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      target.classList.add("revealed");
      return;
    }

    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            if (once) observer?.unobserve(entry.target);
          } else if (!once) {
            entry.target.classList.remove("revealed");
          }
        }
      },
      { threshold },
    );
    observer.observe(target);
  });

  onUnmounted(() => observer?.disconnect());
}
