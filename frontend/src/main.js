// Setup Vue
import Vue from "vue";
import App from "./App.vue";
import router from "./router";
import store from "./store";
import VueChatScroll from "vue-chat-scroll";
// API Calls
import axios from "axios";
// UI Framework
import vuetify from "./plugins/vuetify";
// Form Validation
import VueUtils from "./plugins/vueutils";
import notifications from "./plugins/notifications";
import "./vee-validate";
import "./registerServiceWorker";
import DOMPurify from "dompurify";

// Toast Notifications
import Toast from "vue-toastification";
import "vue-toastification/dist/index.css";

Vue.use(Toast, {
  position: "top-right",
  timeout: 5000,
  maxToasts: 3
});

// Animations
require("animate.css/animate.compat.css");

Vue.use(VueChatScroll);
// Restore legacy notification plugin for backward compatibility
Vue.prototype.$notify = notifications;

// Setup Global Sanitization
Vue.prototype.$sanitize = function(dirty) {
  return DOMPurify.sanitize(dirty);
};

Vue.config.productionTip = false;

// Handle Token Refresh on 401
function createAxiosResponseInterceptor() {
  const interceptor = axios.interceptors.response.use(
    response => response,
    error => {
      // Check if the request explicitly asks to skip the refresh logic
      if (error.config && error.config.skipAuthRefresh) {
        return Promise.reject(error);
      }

      if (error.response && error.response.status !== 401) {
        return Promise.reject(error);
      }

      axios.interceptors.response.eject(interceptor);

      return store
        .dispatch("auth/AUTH_REFRESH")
        .then(() => {
          error.response.config.xsrfCookieName = "csrf_access_token";
          error.response.config.xsrfHeaderName = "X-CSRF-TOKEN";
          return axios(error.response.config);
        })
        .catch(error => {
          if (error.response && error.response.status !== 401) {
            return Promise.reject(error);
          } else {
            store.dispatch("auth/AUTH_LOGOUT");
            router.push("/login");
            return Promise.reject(error);
          }
        })
        .finally(() => {
          createAxiosResponseInterceptor();
        });
    }
  );
}

// Call interceptor
createAxiosResponseInterceptor();
Vue.use(VueUtils);
new Vue({
  router,
  store,
  vuetify,
  render: h => h(App)
}).$mount("#app");
