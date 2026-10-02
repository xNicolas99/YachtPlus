<template>
  <v-navigation-drawer
    v-model="drawer"
    :rail="rail"
    :permanent="$vuetify.display.mdAndUp"
    :temporary="$vuetify.display.smAndDown"
    :width="232"
    class="yp-sidebar"
  >
    <!-- Brand -->
    <div class="yp-brand" :class="{ 'is-rail': rail }">
      <div class="yp-brand-mark" aria-hidden="true"></div>
      <template v-if="!rail">
        <div class="yp-brand-name">YachtPlus</div>
        <div class="yp-brand-ver">v{{ version }}</div>
      </template>
      <v-btn
        :icon="rail ? 'mdi-chevron-right' : 'mdi-chevron-left'"
        :aria-label="rail ? 'Expand sidebar' : 'Collapse sidebar'"
        :title="rail ? 'Expand sidebar' : 'Collapse sidebar'"
        variant="text"
        size="small"
        class="yp-brand-toggle"
        :class="{ 'is-rail': rail }"
        @click.stop="rail = !rail"
      />
    </div>

    <!-- Grouped nav -->
    <nav class="yp-nav">
      <div
        v-for="group in groups"
        :key="group.label"
        class="yp-nav-group"
      >
        <div v-if="!rail" class="yp-nav-title">{{ group.label }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.title"
          v-slot="{ href, navigate, isActive, isExactActive }"
          :to="item.path"
          custom
        >
          <a
            :href="href"
            class="yp-nav-item"
            :class="{ active: item.exact ? isExactActive : isActive }"
            :title="rail ? item.title : undefined"
            @click="navigate"
          >
            <v-icon size="18" class="yp-nav-icon">{{ item.icon }}</v-icon>
            <span v-if="!rail" class="yp-nav-label">{{ item.title }}</span>
            <span
              v-if="!rail && item.count != null"
              class="yp-nav-count yp-mono yp-tnum"
            >{{ item.count }}</span>
          </a>
        </router-link>
      </div>
    </nav>

    <template v-slot:append>
      <v-list density="compact" nav class="yp-side-actions">
        <v-list-item
          prepend-icon="mdi-logout"
          title="Logout"
          @click="logout"
        ></v-list-item>
      </v-list>
    </template>
  </v-navigation-drawer>
</template>

<script>
import { mapActions } from 'vuex';

export default {
  props: {
    modelValue: { type: Boolean, default: null },
  },
  emits: ['update:modelValue'],
  data() {
    return {
      rail: false,
      version: import.meta.env.VITE_VERSION || 'unreleased',
      groups: [
        {
          label: 'Workspace',
          items: [
            { title: 'Dashboard',  icon: 'mdi-view-dashboard',         path: '/',                  exact: true },
            { title: 'Containers', icon: 'mdi-package-variant-closed', path: '/apps' },
            { title: 'Images',     icon: 'mdi-layers',                 path: '/resources/images' },
            { title: 'Volumes',    icon: 'mdi-database',               path: '/resources/volumes' },
            { title: 'Networks',   icon: 'mdi-lan',                    path: '/resources/networks' },
          ],
        },
        {
          label: 'Orchestration',
          items: [
            { title: 'Stacks',    icon: 'mdi-docker',                  path: '/projects' },
            { title: 'Templates', icon: 'mdi-file-document-multiple',  path: '/templates' },
          ],
        },
        {
          label: 'System',
          items: [
            { title: 'Users',    icon: 'mdi-account-multiple', path: '/users' },
            { title: 'Settings', icon: 'mdi-cog',              path: '/settings/info' },
          ],
        },
      ],
    };
  },
  computed: {
    drawer: {
      get() { return this.modelValue; },
      set(value) { this.$emit('update:modelValue', value); },
    },
  },
  methods: {
    ...mapActions('auth', { logout: 'AUTH_LOGOUT' }),
  },
};
</script>

<style scoped>
.yp-sidebar {
  background: var(--yp-bg-2) !important;
  border-right: 1px solid var(--yp-border-soft) !important;
  color: var(--yp-text);
  font-family: var(--yp-font-ui);
}

/* Brand row */
.yp-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 18px;
  border-bottom: 1px solid var(--yp-border-soft);
}
.yp-brand.is-rail { padding: 0 14px; justify-content: center; }
.yp-brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: linear-gradient(135deg, var(--yp-accent) 0%, #6366F1 100%);
  position: relative;
  flex: none;
}
.yp-brand-mark::before {
  content: "";
  position: absolute;
  inset: 5px;
  border-radius: 4px;
  background: var(--yp-bg-2);
}
.yp-brand-mark::after {
  content: "";
  position: absolute;
  top: 10px;
  left: 10px;
  width: 8px;
  height: 8px;
  background: var(--yp-accent);
  border-radius: 2px;
}
.yp-brand-name {
  font-weight: 600;
  letter-spacing: -0.01em;
  font-size: 15px;
}
.yp-brand-ver {
  font-family: var(--yp-font-mono);
  color: var(--yp-muted-2);
  font-size: 10px;
  margin-left: 2px;
  padding: 2px 5px;
  border: 1px solid var(--yp-border-soft);
  border-radius: 4px;
}
.yp-brand-toggle {
  margin-left: auto !important;
  color: var(--yp-muted) !important;
}
.yp-brand-toggle.is-rail {
  margin-left: 0 !important;
}

/* Nav */
.yp-nav {
  padding: 14px 10px;
  overflow-y: auto;
  flex: 1;
}
.yp-nav-group { margin-bottom: 16px; }
.yp-nav-title {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--yp-muted-2);
  padding: 4px 10px 6px;
}
.yp-nav-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 7px 10px;
  border-radius: var(--yp-radius-sm);
  color: var(--yp-muted);
  font-size: 13.5px;
  cursor: pointer;
  position: relative;
  text-decoration: none;
}
.yp-nav-item:hover {
  background: rgba(255, 255, 255, 0.03);
  color: var(--yp-text);
}
.yp-nav-item.active {
  background: var(--yp-accent-soft);
  color: var(--yp-accent);
  font-weight: 500;
}
.yp-nav-item.active::before {
  content: "";
  position: absolute;
  left: -10px;
  top: 6px;
  bottom: 6px;
  width: 2px;
  background: var(--yp-accent);
  border-radius: 0 2px 2px 0;
}
.yp-nav-icon { color: inherit; opacity: 0.85; }
.yp-nav-item.active .yp-nav-icon { opacity: 1; }
.yp-nav-label { flex: 1; min-width: 0; }
.yp-nav-count {
  font-size: 11px;
  color: var(--yp-muted-2);
  padding: 1px 6px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
}
.yp-nav-item.active .yp-nav-count {
  background: rgba(56, 189, 248, 0.18);
  color: var(--yp-accent);
}

/* Footer */
.yp-side-foot {
  padding: 12px 16px;
  border-top: 1px solid var(--yp-border-soft);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--yp-muted);
}
.yp-side-foot.is-rail { justify-content: center; }
.yp-side-ind {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--yp-ok);
  box-shadow: 0 0 0 3px var(--yp-ok-soft);
}
.yp-side-host { color: var(--yp-text); font-weight: 500; }
.yp-side-meta { font-size: 11px; color: var(--yp-muted-2); }
.yp-side-actions { background: transparent !important; }
.yp-col { display: flex; flex-direction: column; }
</style>
