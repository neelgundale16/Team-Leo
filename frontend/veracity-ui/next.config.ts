import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Allow the frontend to call the FastAPI backend on localhost:8000
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/:path*',
      },
    ]
  },

  // Disable strict mode in dev to prevent double SSE connections
  reactStrictMode: false,
}

export default nextConfig