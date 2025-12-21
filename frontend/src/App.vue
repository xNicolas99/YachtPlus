<template>
  <v-app id="yacht">
    <Sidebar v-if="isLoggedIn && $vuetify.breakpoint.mdAndUp" />
    <Bottombar v-if="isLoggedIn && $vuetify.breakpoint.smAndDown" />
    <Appbar v-if="isLoggedIn" />
    <v-main>
      <!-- Provides the application the proper gutter -->
      <v-container fluid>
        <!-- If using vue-router -->
        <transition
          name="slide"
          enter-active-class="animated slideInRight delay"
          leave-active-class="animated slideOutLeft"
        >
          <router-view></router-view>
        </transition>
      </v-container>
    </v-main>
    <snackbar />
  </v-app>
</template>

<script>
import { mapGetters, mapActions } from "vuex";
import Sidebar from "./components/nav/Sidebar";
import Appbar from "./components/nav/Appbar";
import Bottombar from "./components/nav/Bottombar";
import snackbar from "./components/notifications/snackbar";
export default {
  name: "App",

  components: {
    Sidebar: Sidebar,
    Appbar: Appbar,
    Bottombar: Bottombar,
    snackbar: snackbar
  },
  data: () => ({
    refreshTimer: null,
    inactivityTimer: null,
    lastActivity: Date.now(),
    INACTIVITY_LIMIT: 15 * 60 * 1000, // 15 minutes
    REFRESH_INTERVAL: 5 * 60 * 1000 // Refresh token every 5 minutes if active
  }),
  computed: {
    ...mapGetters({
      isLoggedIn: "auth/isAuthenticated",
      authDisabled: "auth/authDisabled"
    }),
    theme() {
      return this.$vuetify.theme.dark ? "dark" : "light";
    }
  },
  methods: {
    ...mapActions({
      authCheck: "auth/AUTH_CHECK",
      refreshToken: "auth/AUTH_REFRESH",
      logout: "auth/AUTH_LOGOUT"
    }),
    resetInactivityTimer() {
      this.lastActivity = Date.now();
    },
    checkActivity() {
      if (!this.isLoggedIn || this.authDisabled) return;

      const now = Date.now();
      const timeSinceActivity = now - this.lastActivity;

      // Check if we should auto-logout
      // Do not logout if on "Logs" page
      if (
        timeSinceActivity > this.INACTIVITY_LIMIT &&
        this.$route.name !== "Logs"
      ) {
        this.logout();
      } else if (timeSinceActivity <= this.INACTIVITY_LIMIT) {
        // User is active, ensure token is refreshed
        // We handle refresh in a separate interval, but we could do it here too.
        // The separate refreshTimer handles the keep-alive.
      }
    },
    handleUserActivity() {
      this.resetInactivityTimer();
    },
    startActivityTracking() {
      window.addEventListener("mousemove", this.handleUserActivity);
      window.addEventListener("click", this.handleUserActivity);
      window.addEventListener("keypress", this.handleUserActivity);
      window.addEventListener("scroll", this.handleUserActivity);
      window.addEventListener("touchstart", this.handleUserActivity);

      // Check for inactivity every minute
      this.inactivityTimer = setInterval(this.checkActivity, 60000);

      // Refresh token periodically if active
      this.refreshTimer = setInterval(() => {
        if (!this.isLoggedIn || this.authDisabled) return;

        const now = Date.now();
        const timeSinceActivity = now - this.lastActivity;

        // If active (within limit) OR if on Logs page (where we assume monitoring is active)
        if (
          timeSinceActivity <= this.INACTIVITY_LIMIT ||
          this.$route.name === "Logs"
        ) {
          this.refreshToken().catch(err => {
            console.warn("Token refresh failed", err);
            // If refresh fails with 401, the interceptor will handle logout
          });
        }
      }, this.REFRESH_INTERVAL);
    },
    stopActivityTracking() {
      window.removeEventListener("mousemove", this.handleUserActivity);
      window.removeEventListener("click", this.handleUserActivity);
      window.removeEventListener("keypress", this.handleUserActivity);
      window.removeEventListener("scroll", this.handleUserActivity);
      window.removeEventListener("touchstart", this.handleUserActivity);

      if (this.inactivityTimer) clearInterval(this.inactivityTimer);
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    },
    updateGlobalBackground() {
      const theme = this.$vuetify.theme.dark ? "dark" : "light";
      const themes = this.$vuetify.theme.themes[theme];
      const bgColor =
        themes.background || (theme === "dark" ? "#0F172A" : "#FFFFFF");

      document.documentElement.style.backgroundColor = bgColor;
      document.body.style.backgroundColor = bgColor;
      // Set CSS variable on root for broader access
      document.documentElement.style.setProperty(
        "--v-background-base",
        bgColor
      );

      const appElement = document.getElementById("app");
      if (appElement) {
        appElement.style.backgroundColor = bgColor;
        appElement.style.minHeight = "100vh";
      }
    }
  },
  watch: {
    isLoggedIn(val) {
      if (val) {
        this.startActivityTracking();
      } else {
        this.stopActivityTracking();
      }
    },
    "$vuetify.theme.dark": "updateGlobalBackground",
    "$vuetify.theme.themes.dark.background": "updateGlobalBackground",
    "$vuetify.theme.themes.light.background": "updateGlobalBackground"
  },
  created() {
    this.authCheck();
    if (this.isLoggedIn) {
      this.startActivityTracking();
    }
    const dark_theme = localStorage.getItem("dark_theme");
    const theme = JSON.parse(localStorage.getItem("theme"));

    if (dark_theme == "false") {
      this.$vuetify.theme.dark = false;
    } else {
      // Default to dark mode if not set or set to true
      this.$vuetify.theme.dark = true;
    }
    if (theme) {
      this.$vuetify.theme.themes = theme;
    }
  },
  mounted() {
    const dark_theme = localStorage.getItem("dark_theme");
    const theme = JSON.parse(localStorage.getItem("theme"));

    if (dark_theme == "false") {
      this.$vuetify.theme.dark = false;
    } else {
      // Default to dark mode
      this.$vuetify.theme.dark = true;
    }
    if (theme) {
      this.$vuetify.theme.themes = theme;
    }
    // Apply background color on mount
    this.$nextTick(() => {
      this.updateGlobalBackground();
    });
  }
};
</script>

<style>
/* Reset body margin/padding to prevent white borders */
body {
  margin: 0;
  padding: 0;
}

.v-application {
  background-color: var(--v-background-base) !important;
}
html,
body,
#app {
  background-color: var(--v-background-base) !important;
  min-height: 100vh;
}
html {
  overflow-y: auto;
}
.animated {
  --animate-duration: 0.3s;
}
.fast-anim {
  --animate-duration: 0.1s;
}
#yacht {
  display: flex;
  width: 100vw;
  min-height: 100vh;
}
.page {
  position: relative;
  flex-grow: 1;
}
.component {
  position: absolute;
  min-width: 100%;
}

/* Global Button Styles for Dark Mode Visibility */
.theme--dark.v-btn:not(.v-btn--flat):not(.v-btn--text):not(.v-btn--outlined):not(.v-btn--icon):not(.v-btn--plain) {
  border: 1px solid rgba(255, 255, 255, 0.2);
}

/* Ensure focus visibility */
.v-btn:focus {
  outline: 2px solid var(--v-primary-base);
  outline-offset: 2px;
}
</style>
