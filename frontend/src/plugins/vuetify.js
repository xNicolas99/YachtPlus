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

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        dark: true,
        colors: {
          primary: savedPrimary || '#1E88E5',
          secondary: savedSecondary || '#43A047',
          accent: '#82B1FF',
          error: '#E53935',
          info: '#2196F3',
          success: '#43A047',
          warning: '#FB8C00',
          surface: '#121212',
          background: '#0A0E27',
        },
      },
      light: {
        dark: false,
        colors: {
          primary: savedPrimary || '#1E88E5',
          secondary: savedSecondary || '#43A047',
          accent: '#82B1FF',
          error: '#E53935',
          info: '#2196F3',
          success: '#43A047',
          warning: '#FB8C00',
          surface: '#FFFFFF',
          background: '#F5F5F5',
        },
      }
    },
  },
})
