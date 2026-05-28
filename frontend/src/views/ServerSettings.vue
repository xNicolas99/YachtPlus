<template lang="html">
  <v-card color="foreground" class="d-flex mx-auto page">
    <v-container fluid class="component">
      <!-- <Nav> was referenced but never imported (Vuetify 2 leftover);
           sidebar is the global nav in Vuetify 3 layout. -->
      <v-card color="foreground" tile>
        <v-row>
          <v-col class="flex-grow-1 flex-shrink-0">
            <div>
              <v-tabs
                v-model="SettingsTab"
                background-color="tabs"
                mobile-breakpoint="sm"
              >
                <v-tab class="text-left" @click="$router.go(-1)">
                  <v-icon left class="mr-1">mdi-arrow-left-bold-outline</v-icon>
                  Back
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-information-outline</v-icon>Info
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-format-color-fill</v-icon>Theme
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-view-list-outline</v-icon
                  >Template Variables
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-trash-can-outline</v-icon>
                  Prune
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-update</v-icon>
                  Update
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-email</v-icon>SMTP
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-shield-lock</v-icon>Security
                </v-tab>
                <v-tab class="text-left">
                  <v-icon left class="mr-1">mdi-history</v-icon>Audit Logs
                </v-tab>
              </v-tabs>
              <!-- Vuetify 3 replaced v-tabs-items / v-tab-item with
                   v-window / v-window-item. The old elements silently
                   render nothing in v3, so every tab past "Info"
                   appeared blank and Audit Logs were unreachable.
                   Migrated to the v3 names; behaviour and the
                   SettingsTab v-model are unchanged. -->
              <v-window v-model="SettingsTab" class="mt-3">
                <v-window-item> </v-window-item>
                <v-window-item>
                  <Info />
                </v-window-item>
                <v-window-item>
                  <Theme />
                </v-window-item>
                <v-window-item>
                  <Variables />
                </v-window-item>
                <v-window-item>
                  <Prune />
                </v-window-item>
                <v-window-item>
                  <Update />
                </v-window-item>
                <v-window-item>
                  <SMTPSettings @notify="notify" />
                </v-window-item>
                <v-window-item>
                  <TwoFactor @notify="notify" />
                </v-window-item>
                <v-window-item>
                  <AuditLogs />
                </v-window-item>
              </v-window>
            </div>
          </v-col>
        </v-row>
        <v-card-text>Version: {{ version }}</v-card-text>
      </v-card>

      <v-snackbar
        v-model="snackbar.show"
        :color="snackbar.color"
        timeout="3000"
      >
        {{ snackbar.message }}
      </v-snackbar>
    </v-container>
  </v-card>
</template>

<script>
import Info from "../components/serverSettings/ServerInfo";
import Variables from "../components/serverSettings/ServerVariables";
import Theme from "../components/serverSettings/Theme";
import Prune from "../components/serverSettings/Prune";
import Update from "../components/serverSettings/ServerUpdate";
import SMTPSettings from "../components/settings/SMTPSettings";
import TwoFactor from "../components/settings/TwoFactor";
import AuditLogs from "../components/serverSettings/AuditLogs.vue";

export default {
  components: {
    Info,
    Variables,
    Theme,
    Prune,
    Update,
    SMTPSettings,
    TwoFactor,
    AuditLogs
  },
  data() {
    return {
      SettingsTab: 1,
      version: import.meta.env.VITE_VERSION || "unreleased",
      snackbar: {
        show: false,
        message: "",
        color: "info"
      }
    };
  },
  methods: {
    notify(data) {
      this.snackbar.message = data.message;
      this.snackbar.color = data.color;
      this.snackbar.show = true;
    }
  }
};
</script>

<style>
.floating-menu {
  z-index: 1;
}
</style>
