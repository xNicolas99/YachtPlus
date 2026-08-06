<template>
  <v-snackbar
    v-model="visible"
    :color="color"
    :location="location"
    :timeout="timeout"
    multi-line
  >
    {{ content }}
    <template v-slot:action>
      <v-btn
        variant="text"
        :color="btnColor"
        @click="clearSnack()"
      >
        Close
      </v-btn>
    </template>
  </v-snackbar>
</template>

<script>
import { mapState, mapMutations } from "vuex";
export default {
  data() {
    return {
      // Vuetify 3 snackbar timeout in ms. -1 disables auto-dismiss.
      timeout: 4000
    };
  },
  computed: {
    ...mapState("snackbar", [
      "content",
      "bottom",
      "color",
      "visible",
      "btnColor"
    ]),
    // Vuetify 3 uses `location` (top/bottom/left/right) instead of the
    // Vuetify 2 `bottom` boolean. Map the legacy store flag to a location.
    location() {
      return this.bottom ? "bottom" : "top";
    }
  },
  methods: {
    ...mapMutations({
      clearSnack: "snackbar/clearSnack"
    })
  }
};
</script>
