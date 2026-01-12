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
          primary: '#00E5FF',
          background: '#0F172A',
        },
      },
      light: {
        dark: false,
        colors: {
          primary: '#00E5FF',
          background: '#FFFFFF',
        },
      }
    },
  },
})
