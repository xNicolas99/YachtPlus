<template>
  <v-app-bar app clipped-left color="secondary">
    <img :src="themeLogo()" class="main-logo" />
    <v-toolbar-title class="ml-2">YachtPlus</v-toolbar-title>

    <!-- Global Search (Hidden on small screens) -->
    <div class="mx-auto hidden-sm-and-down">
      <GlobalSearch />
    </div>

    <v-spacer class="hidden-md-and-up" />
    <v-menu bottom offset-y v-if="!authDisabled">
      <template v-slot:activator="{ on, attrs }">
        <v-btn color="primary" v-bind="attrs" v-on="on" class="pr-2">
          {{ username }}
          <v-icon> mdi-chevron-down </v-icon>
        </v-btn>
      </template>
      <v-list color="foreground">
        <v-list-item :to="{ path: `/user/info` }">
          <v-list-item-icon>
            <v-icon>mdi-account-settings-outline</v-icon>
          </v-list-item-icon>
          <v-list-item-content>
            User
          </v-list-item-content>
        </v-list-item>
        <v-list-item @click="logout()">
          <v-list-item-icon>
            <v-icon>mdi-logout-variant</v-icon>
          </v-list-item-icon>
          <v-list-item-content>
            Logout
          </v-list-item-content>
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
  methods: {
    ...mapActions({
      logout: "auth/AUTH_LOGOUT"
    }),
    themeLogo() {
      if (themeLogo) {
        return themeLogo;
      } else if (this.$vuetify.theme.dark == true) {
        return darkLogo;
      } else if (this.$vuetify.theme.dark == false) {
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
  max-width: 47px;
  max-height: 32px;
}
</style>
