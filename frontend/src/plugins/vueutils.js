import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";
import localizedFormat from "dayjs/plugin/localizedFormat";

dayjs.extend(utc);
dayjs.extend(localizedFormat);

const VueUtils = {
  install(app) {
    // Vue 3 Global Properties
    app.config.globalProperties.$formatDate = (value, format) => {
      if (value) {
        return dayjs(dayjs.utc(value).toDate())
          .local()
          .format(format || "LLL");
      }
      return '';
    };

    app.config.globalProperties.$truncate = (value, limit, suffix) => {
      if (!value) return '';
      if (value.length > limit) {
        let idx = value.lastIndexOf(" ", limit - 1);
        value = value.substring(0, idx ? idx : limit - 1) + (suffix || "…");
      }
      return value;
    };

    // Compat for Vue 2 filters (if still used in templates, will fail in Vue 3 compiler unless migraton build)
    // Vue 3 does not support filters. We must rely on method calls in templates: $formatDate(val)
  }
};

export default VueUtils;
