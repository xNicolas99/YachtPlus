// F48: the old file did `import Vue from "vue"` (Vue 2 API, crashes
// under Vue 3) and was never registered as a plugin, so every
// this.$toast call was a silent no-op. Vue 3 route: export plain
// functions backed by the snackbar Vuex module, which IS registered.
import store from "@/store";

const notify = (type, message) => {
  store.commit(`snackbar/${type}`, { message }, { root: true });
};

export default {
  success: message => notify("setSuccess", message),
  error: message => notify("setErr", message),
  warning: message => notify("setInfo", message),
  info: message => notify("setInfo", message),
};
