import { extend } from "vee-validate";
// import { required, email, max } from "vee-validate/dist/rules";
//
// extend("required", {
//   ...required,
//   message: "This field is required"
// });
//
// extend("max", {
//   ...max,
//   message: "This field must be {length} characters or less"
// });
//
// extend("email", {
//   ...email,
//   message: "This field must be a valid email"
// });
//
// // BUG
// // import { url } from "vee-validate/dist/rules";
// //
// // extend("url", {
// //   ...url,
// //   message: "This is not a valid URL"
// // });

import * as rules from "vee-validate/dist/rules";
import { messages } from "vee-validate/dist/locale/en.json";
Object.keys(rules).forEach(rule => {
  extend(rule, {
    ...rules[rule], // copies rule configuration
    message: messages[rule] // assign message
  });
});

extend("url", {
  validate: str => {
    try {
      const url = new URL(str);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (_) {
      return false;
    }
  },
  message: "This is not a valid URL"
});
