<template>
  <v-app id="yachtplus">
    <!-- Chrome (Sidebar + Appbar) is hidden on the auth-bootstrap
         routes. Previously these were keyed off isLoggedIn only — so if
         a user reloaded with a valid session cookie AND the setup-status
         check returned false (e.g. a backend hiccup or a wiped /config),
         the router redirected to /setup but the dashboard chrome stayed
         on screen, producing the confusing "Setup-Wizard mit normaler UI
         im Hintergrund" state. -->
    <Sidebar
      v-if="showChrome"
      v-model="drawer"
    />

    <Appbar
      v-if="showChrome"
      @toggle-drawer="drawer = !drawer"
    />

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

    <!-- Global snackbar for success/error feedback. Mounted once here so
         every view can push notifications via the snackbar store module
         instead of console.log. -->
    <Snackbar />
  </v-app>
</template>

<script>
import { mapGetters, mapActions } from "vuex";
import Sidebar from "./components/nav/Sidebar.vue";
import Appbar from "./components/nav/Appbar.vue";
import Snackbar from "./components/notifications/snackbar.vue";

export default {
  name: "App",

  components: {
    Sidebar: Sidebar,
    Appbar: Appbar,
    Snackbar: Snackbar
  },
  data: () => ({
    // Initialize drawer to null (Vuetify handles responsive defaults)
    // or false to ensure closed on mobile load.
    drawer: null,
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
    showChrome() {
      // Suppress Sidebar/Appbar during the bootstrap flows. /setup
      // intentionally takes the whole viewport — having the dashboard
      // chrome around it looked like a half-broken render. /login does
      // its own layout. Everything else gets the standard chrome iff
      // the user is actually authenticated.
      if (this.$route.path === "/setup" || this.$route.path === "/login") {
        return false;
      }
      return this.isLoggedIn;
    },
    theme() {
      return this.$vuetify.theme.global.current.dark ? "dark" : "light";
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

      if (
        timeSinceActivity > this.INACTIVITY_LIMIT &&
        this.$route.name !== "Logs"
      ) {
        this.logout();
      }
    },
    handleUserActivity() {
      this.resetInactivityTimer();
    },
    startActivityTracking() {
      // Idempotent: never register the same listeners twice. The old code
      // called this from both `created()` and the `isLoggedIn` watcher, so
      // a login flap could double-register listeners and leak them.
      if (this._activityTrackingStarted) return;
      this._activityTrackingStarted = true;

      window.addEventListener("mousemove", this.handleUserActivity);
      window.addEventListener("click", this.handleUserActivity);
      window.addEventListener("keypress", this.handleUserActivity);
      window.addEventListener("scroll", this.handleUserActivity);
      window.addEventListener("touchstart", this.handleUserActivity);

      this.inactivityTimer = setInterval(this.checkActivity, 60000);

      this.refreshTimer = setInterval(() => {
        if (!this.isLoggedIn || this.authDisabled) return;

        const now = Date.now();
        const timeSinceActivity = now - this.lastActivity;

        if (
          timeSinceActivity <= this.INACTIVITY_LIMIT ||
          this.$route.name === "Logs"
        ) {
          this.refreshToken().catch(err => {
            console.warn("Token refresh failed", err);
          });
        }
      }, this.REFRESH_INTERVAL);
    },
    stopActivityTracking() {
      if (!this._activityTrackingStarted) return;
      this._activityTrackingStarted = false;

      window.removeEventListener("mousemove", this.handleUserActivity);
      window.removeEventListener("click", this.handleUserActivity);
      window.removeEventListener("keypress", this.handleUserActivity);
      window.removeEventListener("scroll", this.handleUserActivity);
      window.removeEventListener("touchstart", this.handleUserActivity);

      if (this.inactivityTimer) clearInterval(this.inactivityTimer);
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    },
    updateGlobalBackground() {
      document.body.style.backgroundColor = this.$vuetify.theme.global.current.colors.background
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
  },
  created() {
    this.authCheck();
    if (this.isLoggedIn) {
      this.startActivityTracking();
    }
  },
  mounted() {
    // Basic theme restoration. The Vuetify 3 theme name is a ref; assign
    // through `.value` when present, otherwise fall back to direct set.
    const dark_theme = localStorage.getItem("dark_theme");
    const targetTheme = dark_theme == "false" ? 'light' : 'dark';

    if (typeof this.$vuetify.theme.global.name === 'object' && 'value' in this.$vuetify.theme.global.name) {
      this.$vuetify.theme.global.name.value = targetTheme;
    } else {
      this.$vuetify.theme.global.name = targetTheme;
    }
  }
};
</script>

<style>
body {
  margin: 0;
  padding: 0;
}
html {
  overflow-y: auto;
}
</style>
