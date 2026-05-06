<template>
  <v-app-bar app clipped-left color="background" elevation="1">
    <!-- Mobile Menu Button (Hamburger) -->
    <v-app-bar-nav-icon aria-label="Toggle navigation menu" title="Toggle navigation menu"
      class="hidden-md-and-up mr-2"
      @click="$emit('toggle-drawer')"
    ></v-app-bar-nav-icon>

    <!-- Logo Section (Only show on mobile or if needed, Sidebar has logo now) -->
    <!-- Showing it on mobile primarily when Sidebar is closed/drawer -->
    <div class="d-flex align-center ml-2 hidden-md-and-up">
      <img :src="themeLogo()" class="main-logo mr-3" alt="YachtPlus Logo" />
      <v-toolbar-title class="font-weight-bold text-h6" style="letter-spacing: 0.5px;">
        YachtPlus
      </v-toolbar-title>
    </div>

    <!-- Spacer for Desktop to align Search -->
    <div class="hidden-sm-and-down ml-4"></div>

    <!-- Global Search (Center) -->
    <v-spacer></v-spacer>
    <div class="hidden-sm-and-down" style="width: 500px; max-width: 100%;">
      <GlobalSearch />
    </div>
    <v-spacer></v-spacer>

    <!-- Right Actions -->
    <div class="d-flex align-center pr-2">
      <!-- Notifications (Placeholder) -->
      <v-btn icon color="medium-emphasis" class="mr-2" aria-label="View notifications" title="View notifications">
        <v-badge content="0" color="error" dot>
          <v-icon>mdi-bell-outline</v-icon>
        </v-badge>
        <v-tooltip activator="parent" location="bottom">Notifications</v-tooltip>
      </v-btn>

      <v-divider vertical inset class="mx-2 hidden-xs"></v-divider>

      <!-- User Dropdown -->
      <v-menu v-if="!authDisabled" offset-y transition="scale-transition">
        <template v-slot:activator="{ props }">
          <v-btn
            color="surface"
            variant="flat"
            class="text-none px-3 ml-2"
            rounded="pill"
            v-bind="props"
          >
            <v-avatar size="32" color="primary" class="mr-2">
              <span class="text-caption text-white font-weight-bold">{{ username.charAt(0).toUpperCase() }}</span>
            </v-avatar>
            <span class="mr-1 hidden-xs text-body-2 font-weight-medium">{{ username }}</span>
            <v-icon size="small" class="ml-1 text-medium-emphasis">mdi-chevron-down</v-icon>
          </v-btn>
        </template>

        <v-list density="compact" rounded="lg" elevation="4" width="200">
          <v-list-subheader class="text-uppercase text-caption">User Account</v-list-subheader>

          <v-list-item :to="{ path: `/user/info` }" prepend-icon="mdi-account-settings-outline">
            <v-list-item-title>Profile Settings</v-list-item-title>
          </v-list-item>

          <v-list-item :to="{ path: `/settings/info` }" prepend-icon="mdi-cog-outline">
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
  computed: {
    ...mapState("auth", ["username", "authDisabled"])
  }
};
</script>

<style scoped>
.main-logo {
  height: 32px;
  width: auto;
  transition: transform 0.2s;
}

.main-logo:hover {
  transform: scale(1.1);
}
</style>
