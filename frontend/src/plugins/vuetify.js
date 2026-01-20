// Styles
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

// Vuetify
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        dark: true,
        colors: {
          primary: '#1E88E5',
          secondary: '#43A047',
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
          primary: '#1E88E5',
          secondary: '#43A047',
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
