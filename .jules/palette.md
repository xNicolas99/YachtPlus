## 2026-05-10 - [Added Visual Feedback for Async Actions]
**Learning:** In Vuetify, when dealing with multiple buttons that trigger async operations (like the resource prune buttons), it's crucial to map the loading state to the specific action being executed to provide clear visual feedback to the user, while simultaneously mapping the disabled state to all action buttons to prevent conflicting concurrent operations.
**Action:** When implementing async groups of actions in the future, track the specific loadingResource to localize the spinner, and utilize a global isLoading flag to disable siblings during the operation.
## 2026-05-07 - Accessibility Attributes on Icon Buttons
**Learning:** Icon-only buttons (like the `mdi-plus` buttons used to deploy apps or create templates) require `aria-label` and `title` attributes for screen readers and tooltips. Adding these micro-UX enhancements improves overall platform usability significantly without altering logic.
**Action:** Always verify `v-btn icon` components have proper `aria-label` and `title` properties in future frontend development steps.
## 2026-05-07 - Small UX improvements for buttons and forms
**Learning:** Found several components where async buttons were missing `:loading` and `:disabled` states (like `Refresh`, `Updates`, and `Generate API Key` buttons). Also found several icon-only buttons missing `aria-label` and `title` tags for accessibility (like the plus and minus buttons for adding rules in forms).
**Action:** Next time check out all the form pages to make sure each async action has the `loading` and `disabled` state.
## 2024-05-13 - [Vuetify Dialog Action Buttons]
**Learning:** In Vuetify component `<v-card-actions>`, it is standard pattern to use the `text` attribute for 'Cancel' buttons to differentiate them from primary actions and prevent visual clutter, especially in destructive dialogs. Furthermore, using semantic colors like `error` is much preferred over hardcoding colors like `red` to correctly support dark mode themes and maintain visual consistency across components.
**Action:** Always ensure that cancellation buttons in `<v-card-actions>` have the `text` attribute and primary/destructive buttons utilize semantic colors like `error` or `primary` rather than hardcoded colors for better accessibility and theme support.
## 2024-05-13 - [Async Login Loading States]
**Learning:** Found that the main login form was missing a loading state for both login and 2FA verification. Adding `:loading` and `:disabled` bindings prevents double-submissions and provides immediate visual feedback during network requests, crucial for authentication flows.
**Action:** Always ensure critical authentication and form submission buttons implement `loading` and `disabled` states bound to a component data variable like `isLoading` set to true at the start of the action and false in the `finally` block.
## 2024-05-13 - [Interactive Icons Accessibility]
**Learning:** Interactive icons must not be implemented as bare `<v-icon @click="...">` tags, as they lack keyboard accessibility, focus states, and semantic roles.
**Action:** Always wrap icon-only actions in `<v-btn icon>` components and explicitly include `aria-label` and `title` attributes for screen readers and tooltips.
