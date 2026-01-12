import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      'vee-validate': path.resolve(__dirname, './src/stubs/vee-validate.js'),
      'vue-chartjs': path.resolve(__dirname, './src/stubs/vue-chartjs.js'),
      'vue-chat-scroll': path.resolve(__dirname, './src/stubs/vue-chat-scroll.js'),
      'vue2-ace-editor': path.resolve(__dirname, './src/stubs/vue2-ace-editor.js'),
    },
    extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
  },
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
