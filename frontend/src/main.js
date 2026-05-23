import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import store from './store'
import vuetify from './plugins/vuetify'
import { loadFonts } from './plugins/webfontloader'
import VueUtils from './plugins/vueutils'
import axios from 'axios'
import DOMPurify from 'dompurify'
import { enforceLinkRelNoopener } from './utils/linkRel'
import './assets/styles/main.css'

// Vee Validate Rules
import { defineRule } from 'vee-validate';
import { required, email, min, max, regex, confirmed } from '@vee-validate/rules';

defineRule('required', required);
defineRule('email', email);
defineRule('min', min);
defineRule('max', max);
defineRule('regex', regex);
defineRule('confirmed', confirmed);

// Load fonts
loadFonts()

const app = createApp(App)

// Global Properties (replacing Vue.prototype)
// Restrict allowed tags/attrs explicitly so v-html cannot reintroduce
// scripts, event handlers, or inline styles via template data.
const SANITIZE_CONFIG = {
  ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'ul', 'ol', 'li', 'code', 'pre'],
  ALLOWED_ATTR: ['href', 'title', 'target', 'rel'],
  ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  FORBID_ATTR: ['style', 'srcset'],
};

// Force rel="noopener noreferrer" on any <a> with a target attribute. A
// template author who writes <a href="..." target="_blank"> would otherwise
// expose the parent window to reverse-tabnabbing — the popup can flip
// window.opener.location and redirect the user away from YachtPlus to a
// phishing page. DOMPurify allows `rel` but does NOT auto-inject it.
// The helper lives in utils/linkRel.js so a unit test can exercise the
// contract without bringing up the full app.
DOMPurify.addHook('afterSanitizeAttributes', enforceLinkRelNoopener);

app.config.globalProperties.$sanitize = function(dirty) {
  return DOMPurify.sanitize(dirty, SANITIZE_CONFIG);
}

// Stub legacy notifications for now
app.config.globalProperties.$notify = function(args) {
  console.log('Notification:', args)
}

// Axios Configuration
const protocol = window.location.protocol;
const hostname = window.location.hostname;
const port = window.location.port ? `:${window.location.port}` : "";
axios.defaults.baseURL = `${protocol}//${hostname}${port}/api`;

// Auth Interceptor
function createAxiosResponseInterceptor() {
  const interceptor = axios.interceptors.response.use(
    response => response,
    error => {
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
createAxiosResponseInterceptor();

const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(store)
app.use(vuetify)
app.use(VueUtils)

app.mount('#app')
