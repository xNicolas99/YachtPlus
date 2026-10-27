<template lang="html">
  <div class="server-settings page">
    <PageHeader title="Server settings" subtitle="Configure your server, security, and appearance.">
      <template #actions><span class="yp-tag" aria-label="YachtPlus version">v{{ version }}</span></template>
    </PageHeader>
    <v-container fluid class="component pa-0">
      <v-card tile>
        <v-row>
          <v-col class="flex-grow-1 flex-shrink-0">
            <div>
              <v-tabs
                v-model="SettingsTab"
              >
                <v-tab class="text-left" @click="$router.go(-1)">
                  <v-icon start class="mr-1">mdi-arrow-left-bold-outline</v-icon>
                  Back
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-information-outline</v-icon>Info
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-format-color-fill</v-icon>Theme
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-view-list-outline</v-icon
                  >Template Variables
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-trash-can-outline</v-icon>
                  Prune
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-update</v-icon>
                  Update
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-email</v-icon>SMTP
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-shield-lock</v-icon>Security
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-history</v-icon>Audit Logs
                </v-tab>
                <v-tab class="text-left">
                  <v-icon start class="mr-1">mdi-calendar-clock</v-icon>Update plans
                </v-tab>
              </v-tabs>
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
                  <NetworkAccessSecurity @notify="notify" />
                  <TwoFactor @notify="notify" />
                </v-window-item>
                <v-window-item>
                  <AuditLogs />
                </v-window-item>
                <v-window-item>
                  <UpdatePlans />
                </v-window-item>
              </v-window>
            </div>
          </v-col>
        </v-row>
      </v-card>

      <v-snackbar
        v-model="snackbar.show"
        :color="snackbar.color"
        :timeout="3000"
      >
        {{ snackbar.message }}
      </v-snackbar>
    </v-container>
  </div>
</template>

<script>
import Info from "../components/serverSettings/ServerInfo";
import Variables from "../components/serverSettings/ServerVariables";
import Theme from "../components/serverSettings/Theme";
import Prune from "../components/serverSettings/Prune";
import Update from "../components/serverSettings/ServerUpdate";
import SMTPSettings from "../components/settings/SMTPSettings";
import TwoFactor from "../components/settings/TwoFactor";
import NetworkAccessSecurity from "../components/settings/NetworkAccessSecurity.vue";
import AuditLogs from "../components/serverSettings/AuditLogs.vue";
import PageHeader from "@/components/PageHeader.vue";
import { defineAsyncComponent } from "vue";
const UpdatePlans = defineAsyncComponent(() => import("../components/serverSettings/UpdatePlans.vue"));

const tabPaths = [null, "/settings/info", "/settings/theme", "/settings/templateVariables",
  "/settings/prune", "/settings/update", "/settings/smtp", "/settings/security", "/settings/audit", "/settings/update-plans"];

export default {
  components: {
    PageHeader,
    UpdatePlans,
    Info,
    Variables,
    Theme,
    Prune,
    Update,
    SMTPSettings,
    TwoFactor,
    NetworkAccessSecurity,
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
  watch: {
    "$route.path": {
      immediate: true,
      handler(path) {
        const tab = tabPaths.indexOf(path);
        this.SettingsTab = tab > 0 ? tab : 1;
      }
    },
    SettingsTab(tab) {
      const path = tabPaths[tab];
      if (path && path !== this.$route.path) this.$router.replace(path);
    }
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
