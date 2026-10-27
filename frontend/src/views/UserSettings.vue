<template lang="html">
  <div class="user-settings page">
    <PageHeader title="Account" subtitle="Manage your profile and sign-in settings.">
      <template v-if="username" #actions><span class="yp-tag">{{ username }}</span></template>
    </PageHeader>
    <v-container fluid class="component pa-0">
      <v-card tile>
        <Nav />
        <v-row>
          <v-col class="flex-grow-1 flex-shrink-0">
            <v-card-text>
              <transition
                name="slide"
                enter-active-class="animated fadeIn delay"
                leave-active-class="animated fadeOut"
                mode="out-in"
              >
                <router-view :currentUsername="username" />
              </transition>
            </v-card-text>
          </v-col>
        </v-row>
      </v-card>
    </v-container>
  </div>
</template>

<script>
import { mapState } from "vuex";
import UserSettingsNav from "../components/userSettings/UserSettingsNav";
import PageHeader from "@/components/PageHeader.vue";
export default {
  components: {
    PageHeader,
    Nav: UserSettingsNav
  },
  computed: {
    ...mapState("auth", ["username"])
  }
};
</script>

<style></style>
