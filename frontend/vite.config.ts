import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { visualizer } from 'rollup-plugin-visualizer'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  return {
    plugins: [
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
        imports: ['vue', 'vue-router', 'pinia'],
        dts: 'src/auto-imports.d.ts',
      }),
      Components({
        resolvers: [ElementPlusResolver()],
        dts: 'src/components.d.ts',
      }),
      visualizer({
        open: false,
        gzipSize: true,
        brotliSize: true,
        filename: 'dist/stats.html',
      }),
    ],
    build: {
      emptyOutDir: true,
      target: 'es2022',
      cssCodeSplit: true,
      sourcemap: false,
      rollupOptions: {
        output: {
          chunkFileNames: 'js/[name]-[hash].js',
          entryFileNames: 'js/[name]-[hash].js',
          assetFileNames: '[ext]/[name]-[hash].[ext]',
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            if (id.includes('/echarts/') || id.includes('/zrender/') || id.includes('/tslib/')) return 'vendor-echarts'
            if (id.includes('/ol/')) return 'vendor-openlayers'
            if (id.includes('/element-plus/') || id.includes('/@element-plus/')) return 'vendor-element'
            if (id.includes('/vue/') || id.includes('/@vue/') || id.includes('/vue-router/') || id.includes('/pinia/')) return 'vendor-framework'
            if (id.includes('/axios/')) return 'vendor-axios'
            return 'vendor-misc'
          },
        },
      },
    },
    optimizeDeps: {
      include: ['ol', 'echarts', 'vue-echarts', 'zrender', 'element-plus/es/locale/lang/zh-cn']
    },
    resolve: {
      dedupe: ['vue', 'vue-router', 'pinia', 'element-plus'],
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      headers: {
        'Cross-Origin-Opener-Policy': 'same-origin',
        'Cross-Origin-Embedder-Policy': 'credentialless',
      },
      proxy: {
        '/api': {
          target: env.VITE_DEV_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
