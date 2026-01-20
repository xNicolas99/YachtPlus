<template>
  <v-app id="yacht">
    <Sidebar v-if="isLoggedIn && $vuetify.display.mdAndUp" />
    <Bottombar v-if="isLoggedIn && $vuetify.display.smAndDown" />
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
    <div style="display:none;">Stub Snackbar</div>
  </v-app>
</template>

<script>
import { mapGetters, mapActions } from "vuex";
import Sidebar from "./components/nav/Sidebar.vue";
import Appbar from "./components/nav/Appbar.vue";
import Bottombar from "./components/nav/Bottombar.vue";

export default {
  name: "App",

  components: {
    Sidebar: Sidebar,
    Appbar: Appbar,
    Bottombar: Bottombar
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
      window.removeEventListener("mousemove", this.handleUserActivity);
      window.removeEventListener("click", this.handleUserActivity);
      window.removeEventListener("keypress", this.handleUserActivity);
      window.removeEventListener("scroll", this.handleUserActivity);
      window.removeEventListener("touchstart", this.handleUserActivity);

      if (this.inactivityTimer) clearInterval(this.inactivityTimer);
      if (this.refreshTimer) clearInterval(this.refreshTimer);
    },
    updateGlobalBackground() {
      // Stub for now, Vuetify 3 handles theme differently
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
    // Basic theme restoration
    const dark_theme = localStorage.getItem("dark_theme");
    // Fix: direct assignment if not a ref, or handle ref
    const targetTheme = dark_theme == "false" ? 'light' : 'dark';
    // Check if name is an object (ref) or string
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
