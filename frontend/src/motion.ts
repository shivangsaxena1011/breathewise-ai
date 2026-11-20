/** True when the user asked the OS to minimise animation. */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** Smooth scrolling, unless the user prefers reduced motion. */
export function scrollBehavior(): ScrollBehavior {
  return prefersReducedMotion() ? "auto" : "smooth";
}
