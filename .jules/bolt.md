## 2024-05-24 - [Optimize GlobalSearch.vue API fetches]
**Learning:** Found a significant anti-pattern in `GlobalSearch.vue` where multiple independent network requests (`/containers` and `/search`) were being fetched sequentially inside a debounced method. Additionally, it fetched the entire `/templates` list redundantly because the backend `/search` endpoint already returned templates. This delayed search results unnecessarily.
**Action:** When implementing global or multi-source searches, avoid redundant fetches if the unified endpoint covers them. Use `Promise.all` to fetch independent data sources concurrently, minimizing the time to interactive.

## 2025-05-07 - Avoid Redundant Backend Queries for Search
**Learning:** `GlobalSearch.vue` and `UnifiedSearch.vue` components frequently re-query the backend `/containers` endpoint on keystrokes, which creates performance bottlenecks since the container data is already available locally in the Vuex store (`store.state.apps.apps`).
**Action:** When implementing search functionalities in the frontend, query running containers locally using the Vuex store instead of calling the `/containers` API endpoint on every keystroke. Concurrency via `Promise.all()` should only be used when strictly necessary for external/unified searches.
