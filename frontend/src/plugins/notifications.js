import Vue from 'vue';

export default {
  success: (message) => { if(Vue.prototype.$toast) Vue.prototype.$toast.success(message) },
  error: (message) => { if(Vue.prototype.$toast) Vue.prototype.$toast.error(message) },
  warning: (message) => { if(Vue.prototype.$toast) Vue.prototype.$toast.warning(message) },
  info: (message) => { if(Vue.prototype.$toast) Vue.prototype.$toast.info(message) },
};
