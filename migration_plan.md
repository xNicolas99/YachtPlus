# Migration Plan: Vue 2 to Vue 3 (Vite + Vuetify 3)

**Author:** Jules (Lead Architect)
**Date:** December 2025

## 1. Executive Summary
The current frontend is built on **Vue 2**, which reached End-Of-Life (EOL) in December 2023. This poses critical security risks. The build system (Webpack/Vue CLI) is outdated and slow. This plan outlines the steps to migrate to **Vue 3**, **Vite**, and **Vuetify 3**.

## 2. Technical Stack Changes

| Component | Current | Target |
| :--- | :--- | :--- |
| **Framework** | Vue 2.7.16 | **Vue 3.4+** |
| **UI Library** | Vuetify 2.7.2 | **Vuetify 3.6+** |
| **Build Tool** | Vue CLI (Webpack) | **Vite 5+** |
| **State Management** | Vuex 3 | **Pinia** (Recommended) or Vuex 4 |
| **Router** | Vue Router 3 | **Vue Router 4** |
| **Icons** | MDI / FontAwesome | **Unplugin-Icons** / MDI |

## 3. Migration Roadmap

### Phase 1: Initialization & Infrastructure
1.  **Initialize New Project**: Do not try to upgrade the existing `package.json` in place. Create a fresh project using `npm create vue@latest`.
    *   Select: Vue 3, TypeScript (Recommended) or JavaScript, Vue Router, Pinia.
2.  **Install Vuetify 3**: `npm install vuetify@next mdi`.
3.  **Configure Vite**: Setup `vite.config.js` to proxy `/api` requests to `http://localhost:8000`.

### Phase 2: Core Migration (The "Hard" Part)
1.  **Global Config**: Move logic from `main.js` to `main.ts`.
    *   Replace `Vue.prototype.$sanitize` with `app.config.globalProperties.$sanitize`.
    *   Replace `Vue.use(...)` with `app.use(...)`.
2.  **Router**: Rewrite `router/index.js` to use `createRouter` and `createWebHistory`.
    *   Update navigation guards.
3.  **Store**: Convert Vuex modules to Pinia stores (or upgrade to Vuex 4).
    *   *Tip:* Pinia is significantly easier to type and maintain.

### Phase 3: Component Migration
1.  **SFC Syntax**:
    *   Convert `<script>` to `<script setup>` (Composition API) is recommended but Options API is still supported.
    *   **Breaking Change**: `v-model` in Vue 3 uses `modelValue` prop and `update:modelValue` event.
    *   **Breaking Change**: `.native` modifier is removed.
2.  **Vuetify Updates**:
    *   Grid system: `<v-layout>` -> `<v-container>`, `<v-flex>` -> `<v-col>`.
    *   Colors: Theme configuration has moved to `createVuetify({ theme: { ... } })`.
    *   Components: Check Vuetify 3 Migration Guide for specific prop changes (e.g., `v-btn` props).

### Phase 4: Third-Party Libraries
1.  **Vue-Toastification**: Upgrade to Vue 3 compatible version or switch to `vuetify-sonner`.
2.  **ApexCharts**: Ensure `vue3-apexcharts` is used.
3.  **XTerm.js**: The wrapper component needs to be rewritten using the Composition API to correctly handle lifecycle hooks (`onMounted`, `onBeforeUnmount`).

## 4. Specific Code Changes Required

### API Client
*   Axios interceptors in `main.js` need to be moved to a composable (e.g., `useApi.js`) or a dedicated service file that imports the Router instance directly, as `this` context is not available in Composition API setup.

### Authentication
*   The `check_setup_status` logic in `App.vue` or `router` needs to be preserved. Ensure Pinia auth store is initialized before the router guard runs.

## 5. Execution Strategy
*   **Parallel Development**: Create a `frontend-v3` folder. Develop the new frontend alongside the old one.
*   **Incremental Porting**: Port views one by one:
    1.  Login / Setup (Critical Path)
    2.  Dashboard
    3.  Applications List
    4.  Container Details / Terminal
    5.  Settings
*   **Cutover**: Once feature parity is reached, replace the `frontend` folder build artifact in the Dockerfile.

## 6. Resources
*   [Vue 3 Migration Guide](https://v3.vuejs.org/guide/migration/introduction.html)
*   [Vuetify 3 Upgrade Guide](https://vuetifyjs.com/en/getting-started/upgrade-guide/)
*   [Vite Documentation](https://vitejs.dev/)

**Signed:**
*Jules, Lead Architect*
