import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import localizedFormat from "dayjs/plugin/localizedFormat";

dayjs.extend(utc);
dayjs.extend(localizedFormat);

const VueUtils = {
  install(app) {
    app.config.globalProperties.$formatDate = (value, format) => {
      if (value) {
        return dayjs.utc(value).local().format(format || "LLL");
      }
      return '';
    };

    app.config.globalProperties.$truncate = (value, limit, suffix) => {
      if (!value) return '';
      value = value.toString();
      if (value.length > limit) {
        let idx = value.lastIndexOf(" ", limit - 1);
        // Ensure we don't cut off at the very beginning if no space found
        value = value.substring(0, idx > 0 ? idx : limit - 1) + (suffix || "…");
      }
      return value;
    };
  }
};

export default VueUtils;
