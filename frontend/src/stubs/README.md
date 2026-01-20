The following libraries are currently stubbed/shimmed in this repository due to the migration to Vue 3:

*   `vee-validate`: Replaced with a shim that renders valid Vue 3 components but **disables validation**. Forms will submit without client-side checks.
*   `vue-chartjs`: Replaced with a placeholder component. Charts will not render.
*   `vue2-ace-editor`: Replaced with a simple `<textarea>`. No syntax highlighting.
*   `vue-chat-scroll`: Replaced with a basic directive that attempts to scroll to bottom.

These shims were implemented to allow the application to build and run without crashing. Future work is required to fully migrate these dependencies to their Vue 3 equivalents (`vee-validate` v4, `vue-chartjs` v5, `vue3-ace-editor`).
