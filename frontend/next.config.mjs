/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  compiler: {
    styledComponents: true,
  },
  async rewrites() {
    // Use environment variable for backend URL, fallback to localhost
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    // Convert http://localhost:8000 to http://127.0.0.1:8000 for proxy
    const proxyUrl = backendUrl.replace('localhost', '127.0.0.1');
    
    return [
      {
        source: '/api/:path*',
        destination: `${proxyUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
