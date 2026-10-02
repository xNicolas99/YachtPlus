import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import path from 'path'
import { fileURLToPath } from 'url'
import { readFileSync } from 'node:fs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const { version } = JSON.parse(readFileSync(path.join(__dirname, 'package.json'), 'utf8'))
const displayVersion = process.env.VITE_VERSION || version

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    {
      name: 'yachtplus-build-version',
      apply: 'build',
      generateBundle() {
        this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ version: displayVersion }) + '\n' })
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue']
  },
  optimizeDeps: {
    esbuildOptions: {
      define: {
        global: 'globalThis'
      }
    }
  },
  test: {
    // Vuetify auto-imports CSS from its ESM modules while compiling .vue
    // components; Vitest must transform those modules instead of asking Node
    // to load CSS directly.
    server: { deps: { inline: ['vuetify'] } },
  },
  build: {
    manifest: true,
    commonjsOptions: {
      transformMixedEsModules: true,
    },
    rollupOptions: {
      output: {
        // Split heavy vendor libs into their own cacheable chunks so the
        // initial bundle stays small and unchanged vendors are re-used
        // across deploys (long-lived HTTP cache).
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'vuex'],
          'vuetify': ['vuetify'],
          'axios': ['axios'],
        },
      },
    },
  },
  define: {
    'process.env': {},
    'import.meta.env.VITE_VERSION': JSON.stringify(displayVersion),
  },
  server: {
    port: 8080,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
