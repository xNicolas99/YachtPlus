import Vue from 'vue';
import Toast from 'vue-toastification';
import 'vue-toastification/dist/index.css';

Vue.use(Toast, {
  position: 'top-right',
  timeout: 3000,
});

export default {
  success: (message) => Vue.$toast.success(message),
  error: (message) => Vue.$toast.error(message),
  warning: (message) => Vue.$toast.warning(message),
  info: (message) => Vue.$toast.info(message),
};
