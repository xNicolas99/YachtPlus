// Styles
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

// Vuetify
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

// Helper to update theme dynamically
export function updateTheme(vuetifyInstance, primaryColor, secondaryColor) {
  if (!vuetifyInstance) return;
  const themes = ['light', 'dark'];
  themes.forEach(t => {
    if (vuetifyInstance.theme.themes.value[t]) {
      if (primaryColor) vuetifyInstance.theme.themes.value[t].colors.primary = primaryColor;
      if (secondaryColor) vuetifyInstance.theme.themes.value[t].colors.secondary = secondaryColor;
    }
  });
}

// Load saved colors
const savedPrimary = localStorage.getItem('theme_primary');
const savedSecondary = localStorage.getItem('theme_secondary');

// Palette synchronised with src/assets/styles/yp-design.css (the INDEX
// Overhaul design tokens). When components use Vuetify color names like
// `color="primary"` or `bg-surface` they will pick these up automatically;
// raw markup that needs the exact same colours can use the --yp-* CSS
// variables defined in yp-design.css.
export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        dark: true,
        colors: {
          primary:    savedPrimary   || '#38BDF8', // sky-400 — design accent
          secondary:  savedSecondary || '#A78BFA', // violet-400 — secondary accent
          accent:     '#38BDF8',
          error:      '#EF4444',
          info:       '#38BDF8',
          success:    '#22C55E',
          warning:    '#F59E0B',
          surface:    '#1E293B', // slate-800 — cards
          background: '#0F172A', // slate-900 — app background
        },
      },
      light: {
        dark: false,
        colors: {
          primary:    savedPrimary   || '#0EA5E9',
          secondary:  savedSecondary || '#7C3AED',
          accent:     '#0EA5E9',
          error:      '#DC2626',
          info:       '#0EA5E9',
          success:    '#16A34A',
          warning:    '#D97706',
          surface:    '#FFFFFF',
          background: '#F8FAFC',
        },
      }
    },
  },
})
