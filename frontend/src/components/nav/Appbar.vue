<template>
  <v-app-bar app clipped-left flat height="56" class="yp-topbar">
    <!-- Mobile hamburger -->
    <v-app-bar-nav-icon
      aria-label="Toggle navigation menu"
      title="Toggle navigation menu"
      class="hidden-md-and-up mr-2"
      @click="$emit('toggle-drawer')"
    ></v-app-bar-nav-icon>

    <!-- Mobile brand -->
    <div class="d-flex align-center ml-2 hidden-md-and-up">
      <img :src="themeLogo()" class="main-logo mr-3" alt="YachtPlus Logo" />
      <v-toolbar-title class="font-weight-bold" style="letter-spacing: 0.5px;">
        YachtPlus
      </v-toolbar-title>
    </div>

    <!-- Search (center) -->
    <v-spacer></v-spacer>
    <div class="hidden-sm-and-down yp-search-wrap">
      <GlobalSearch />
    </div>
    <v-spacer></v-spacer>

    <!-- Host indicator -->
    <div class="yp-host hidden-sm-and-down mr-3" title="Active host">
      <span class="yp-host-dot" aria-hidden="true"></span>
      <span class="yp-host-name">{{ hostLabel }}</span>
      <span class="yp-host-meta yp-mono">{{ hostMeta }}</span>
      <v-icon size="14" color="medium-emphasis">mdi-chevron-down</v-icon>
    </div>

    <!-- Right actions -->
    <div class="d-flex align-center pr-2">
      <v-btn
        icon
        variant="text"
        class="mr-2 yp-iconbtn"
        aria-label="View notifications"
        title="View notifications"
      >
        <!-- :model-value gates the badge entirely. Vuetify 3's `dot` mode
             draws the badge unconditionally when the model is truthy
             regardless of `content`, so `content="0"` was NOT enough to
             hide it — the small blue dot showed even with zero unread.
             Bind to a real unread count once the notification stream is
             implemented; for now keep the badge off. -->
        <v-badge :model-value="hasUnreadNotifications" color="primary" dot offset-x="2" offset-y="2">
          <v-icon>mdi-bell-outline</v-icon>
        </v-badge>
        <v-tooltip activator="parent" location="bottom">Notifications</v-tooltip>
      </v-btn>

      <!-- User dropdown -->
      <v-menu v-if="!authDisabled" offset-y transition="scale-transition">
        <template v-slot:activator="{ props }">
          <v-btn
            color="surface"
            variant="flat"
            class="text-none px-3 ml-1 yp-user-btn"
            rounded="pill"
            v-bind="props"
          >
            <v-avatar size="28" class="mr-2 yp-avatar">
              <span class="text-caption font-weight-bold">{{ usernameInitial }}</span>
            </v-avatar>
            <span class="mr-1 hidden-xs text-body-2 font-weight-medium">{{ username }}</span>
            <v-icon size="small" class="ml-1 text-medium-emphasis">mdi-chevron-down</v-icon>
          </v-btn>
        </template>

        <v-list density="compact" rounded="lg" elevation="4" width="200">
          <v-list-subheader class="text-uppercase text-caption">User Account</v-list-subheader>

          <v-list-item :to="{ path: '/user/info' }" prepend-icon="mdi-account-settings-outline">
            <v-list-item-title>Profile Settings</v-list-item-title>
          </v-list-item>

          <v-list-item :to="{ path: '/settings/info' }" prepend-icon="mdi-cog-outline">
            <v-list-item-title>System Settings</v-list-item-title>
          </v-list-item>

          <v-divider class="my-2"></v-divider>

          <v-list-item @click="logout()" prepend-icon="mdi-logout-variant" class="text-error">
            <v-list-item-title>Logout</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>
  </v-app-bar>
</template>

<script>
import { mapActions, mapState } from "vuex";
import lightLogo from "@/assets/logo-light.svg";
import darkLogo from "@/assets/logo.svg";
import { themeLogo } from "../../config.js";
import GlobalSearch from "@/components/GlobalSearch.vue";

export default {
  components: {
    GlobalSearch
  },
  emits: ['toggle-drawer'],
  data() {
    return {
      // Static placeholders matching the INDEX Overhaul mock. Wire to a real
      // hosts store once the multi-host backend lands.
      hostLabel: window.location.hostname || 'localhost',
      hostMeta: window.location.hostname || '10.0.4.18',
      // Wired to a real source the day the notification feature lands.
      // Until then keep the badge off so it doesn't lie to the user.
      hasUnreadNotifications: false,
    };
  },
  computed: {
    ...mapState("auth", ["username", "authDisabled"]),
    usernameInitial() {
      return (this.username || 'U').charAt(0).toUpperCase();
    },
  },
  methods: {
    ...mapActions({
      logout: "auth/AUTH_LOGOUT"
    }),
    themeLogo() {
      if (themeLogo) {
        return themeLogo;
      } else if (this.$vuetify.theme.global.current.dark) {
        return darkLogo;
      } else {
        return lightLogo;
      }
    }
  },
};
</script>

<style scoped>
.yp-topbar {
  background: var(--yp-bg) !important;
  border-bottom: 1px solid var(--yp-border-soft) !important;
  color: var(--yp-text);
}
.main-logo {
  height: 32px;
  width: auto;
  transition: transform 0.2s;
}
.main-logo:hover { transform: scale(1.05); }

.yp-search-wrap {
  width: 420px;
  max-width: 100%;
}

/* Host indicator */
.yp-host {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 12px;
  background: var(--yp-surface);
  border: 1px solid var(--yp-border-soft);
  border-radius: var(--yp-radius-sm);
  font-size: 13px;
  color: var(--yp-text);
  cursor: pointer;
}
.yp-host:hover { background: var(--yp-surface-2); }
.yp-host-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--yp-ok);
  box-shadow: 0 0 0 3px var(--yp-ok-soft);
}
.yp-host-name { font-weight: 500; }
.yp-host-meta {
  color: var(--yp-muted);
  font-size: 11px;
}

/* Right actions */
.yp-iconbtn { color: var(--yp-muted) !important; }
.yp-iconbtn:hover { color: var(--yp-text) !important; }
.yp-user-btn { border: 1px solid var(--yp-border-soft); }
.yp-avatar {
  background: linear-gradient(135deg, #475569, #1e293b);
  border: 1px solid var(--yp-border);
  color: var(--yp-text) !important;
}
</style>
