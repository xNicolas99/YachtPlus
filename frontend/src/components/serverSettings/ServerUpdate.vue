<template>
  <v-card color="foreground">
    <v-fade-transition>
      <v-progress-linear
        indeterminate
        v-if="isLoading"
        color="primary"
        bottom
      />
    </v-fade-transition>
    <v-card-title class="subheading primary font-weight-bold"
      >Update</v-card-title
    >
    <v-card-text class="mt-2"
      >Update YachtPlus to the latest version. <br />
      This starts a temporary update worker through the configured Docker proxy.
      In the process YachtPlus will be restarted and you will be logged
      out.</v-card-text
    >
    <v-btn
      class="mx-5 mb-5"
      color="primary"
      @click="update()"
      :disabled="!updatable"
    >
      Update YachtPlus
    </v-btn>
  </v-card>
</template>

<script>
import axios from "axios";
import { mapMutations, mapActions, mapState } from "vuex";
export default {
  data() {
    return {
      containerDialog: false,
      isLoading: false,
      updatable: false
    };
  },
  mounted() {
    this.checkUpdate();
  },
  computed: {
    ...mapState("auth", ["authDisabled"])
  },
  methods: {
    ...mapMutations({
      setMessage: "snackbar/setMessage",
      setErr: "snackbar/setErr"
    }),
    ...mapActions({
      logout: "auth/AUTH_LOGOUT"
    }),
    checkUpdate() {
      this.isLoading = true;
      axios({
        url: "/settings/check/update",
        method: "GET"
      })
        .then(response => {
          this.isLoading = false;
          this.updatable = response.data;
        })
        .catch(err => {
          this.isLoading = false;
          this.setErr(err);
        });
    },
    async update() {
      this.isLoading = true;
      try {
        await axios.post("/settings/update");
        this.setMessage("YachtPlus accepted the update. Check the updater container for its result.");
        await new Promise(resolve => setTimeout(resolve, 5000));
        if (!this.authDisabled) await this.logout();
      } catch (err) {
        this.setErr(err);
      } finally {
        this.isLoading = false;
      }
    }
  }
};
</script>
