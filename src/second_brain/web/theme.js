"use strict";
(() => {
  // Only a theme name is persisted; content, filters and queries stay in page memory.
  let theme = "light";
  try {
    const saved = localStorage.getItem("second-brain-theme");
    if (["light", "dark", "latte"].includes(saved)) theme = saved;
  } catch { /* The reader also works when browser storage is unavailable. */ }
  document.documentElement.dataset.theme = theme;
})();
