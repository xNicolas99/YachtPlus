import { format, parseISO } from "date-fns";

const VueUtils = {
  install(app) {
    app.config.globalProperties.$formatDate = (value, formatStr) => {
      if (value) {
        try {
          const date = typeof value === 'string' ? parseISO(value) : value;
          return format(date, formatStr || "PPpp");
        } catch (e) {
          console.error("Date format error:", e);
          return value;
        }
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
