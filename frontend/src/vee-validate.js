import { defineRule, configure } from "vee-validate";
import { all } from "@vee-validate/rules";
import { localize } from '@vee-validate/i18n';
import en from '@vee-validate/i18n/dist/locale/en.json';

// Install all rules
Object.entries(all).forEach(([name, rule]) => {
  defineRule(name, rule);
});

// Configure messages
configure({
  generateMessage: localize({
    en,
  }),
});

defineRule("url", (value) => {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") || "This is not a valid URL";
  } catch (_) {
    return "This is not a valid URL";
  }
});
