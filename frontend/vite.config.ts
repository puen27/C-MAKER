import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// 개발 서버에서는 /api 요청을 로컬 FastAPI(127.0.0.1:8000)로 넘긴다. 운영은 Nginx가 같은 역할을 한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
