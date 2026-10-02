import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
dayjs.extend(relativeTime);
const dateValue = value => typeof value === 'number' && value < 1e12 ? value * 1000 : value;

export default {
  install(app) {
    app.config.globalProperties.$formatDate = (value, format = 'YYYY-MM-DD HH:mm:ss') => {
      if (!value) return '';
      return dayjs(dateValue(value)).format(format);
    };
    app.config.globalProperties.$timeAgo = (value) => {
      if (!value) return '';
      return dayjs(dateValue(value)).fromNow();
    };
    app.config.globalProperties.$truncate = (text, length, clamp = '...') => {
      return text?.length > length ? text.slice(0, length) + clamp : text;
    };
  }
};
