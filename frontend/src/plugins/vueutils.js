import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);

export default {
  install(app) {
    app.config.globalProperties.$formatDate = (value, format = 'YYYY-MM-DD HH:mm:ss') => {
      if (!value) return '';
      return dayjs(value).format(format);
    };
    app.config.globalProperties.$timeAgo = (value) => {
      if (!value) return '';
      return dayjs(value).fromNow();
    };
    app.config.globalProperties.$truncate = (text, length, clamp = '...') => {
      return text?.length > length ? text.slice(0, length) + clamp : text;
    };
  }
};
