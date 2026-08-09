import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { visualizer } from 'rollup-plugin-visualizer'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const isProd = mode === 'production'
  return {
    esbuild: {
      // P1-20: 生产环境移除 console/debugger（与 mobile 一致）
      drop: isProd ? ['console', 'debugger'] : [],
    },
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
      // FIX: [验收] 移除 dev server 的 Cross-Origin-Embedder-Policy 头。
      // credentialless COEP 会阻止天地图等跨域地图瓦片加载（天地图服务器不返回 CORP 头），
      // 导致 /map 页面 20 个控制台 error。COOP same-origin 保留（不影响跨域图片）。
      // 生产环境通过 nginx 按需配置 COEP（仅视频播放页需要 SharedArrayBuffer）。
      headers: {
        'Cross-Origin-Opener-Policy': 'same-origin',
      },
      proxy: {
        // FIX: [验收] 改为 '/api/'（带斜杠），避免匹配到 /api-keys 等前端路由路径。
        // 原配置 '/api' 会把 /api-keys 导航请求代理到后端返回 404。
        '/api/': {
          target: env.VITE_DEV_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
