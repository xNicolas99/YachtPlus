import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import vuetify from './plugins/vuetify'
import { loadFonts } from './plugins/webfontloader'
import VueUtils from './plugins/vueutils'
import axios from 'axios'
import DOMPurify from 'dompurify'
import './assets/styles/main.css'

// Load fonts
loadFonts()

const app = createApp(App)

// Global Properties (replacing Vue.prototype)
app.config.globalProperties.$sanitize = function(dirty) {
  return DOMPurify.sanitize(dirty);
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

app.use(router)
app.use(store)
app.use(vuetify)
app.use(VueUtils)

app.mount('#app')
