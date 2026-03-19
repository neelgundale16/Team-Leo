import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Proxy /api/* → backend so there is zero CORS issue
  async rewrites() {
    return [
      {
        source:      '/api/:path*',
        destination: 'http://127.0.0.1:8000/:path*',
      },
    ]
  },

  // Disable strict mode — prevents double SSE connections in dev
  reactStrictMode: false,
}

export default nextConfig