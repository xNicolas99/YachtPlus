<template>
  <v-app-bar app clipped-left color="background" elevation="1">
    <!-- Mobile Menu Button -->
    <v-app-bar-nav-icon
      class="hidden-md-and-up"
      @click="$emit('toggle-drawer')"
    ></v-app-bar-nav-icon>

    <!-- Logo -->
    <div class="d-flex align-center ml-2">
      <img :src="themeLogo()" class="main-logo mr-3" alt="YachtPlus Logo" />
      <v-toolbar-title class="font-weight-bold text-h6" style="letter-spacing: 0.5px;">
        YachtPlus
      </v-toolbar-title>
    </div>

    <v-spacer></v-spacer>

    <!-- Global Search (Center) -->
    <div class="hidden-sm-and-down mx-4" style="width: 400px; max-width: 100%;">
      <GlobalSearch />
    </div>

    <v-spacer></v-spacer>

    <!-- User Dropdown -->
    <v-menu v-if="!authDisabled" offset-y transition="scale-transition">
      <template v-slot:activator="{ props }">
        <v-btn
          color="surface"
          variant="flat"
          class="text-none px-3"
          rounded="pill"
          v-bind="props"
        >
          <v-avatar size="32" color="primary" class="mr-2">
            <span class="text-caption text-white font-weight-bold">{{ username.charAt(0).toUpperCase() }}</span>
          </v-avatar>
          <span class="mr-1 hidden-xs">{{ username }}</span>
          <v-icon size="small">mdi-chevron-down</v-icon>
        </v-btn>
      </template>

      <v-list density="compact" rounded="lg" elevation="4">
        <v-list-item :to="{ path: `/user/info` }" prepend-icon="mdi-account-settings-outline">
          <v-list-item-title>Profile</v-list-item-title>
        </v-list-item>
        <v-divider class="my-1"></v-divider>
        <v-list-item @click="logout()" prepend-icon="mdi-logout-variant" color="error">
          <v-list-item-title>Logout</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-menu>
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
  height: 40px;
  width: auto;
  transition: transform 0.2s;
}

.main-logo:hover {
  transform: scale(1.1);
}
</style>
