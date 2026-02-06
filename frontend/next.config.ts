import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for production Docker images (small runtime image).
  output: "standalone",
  // Reduce cache times in development to prevent stale data issues
  experimental: {
    staleTimes: {
      dynamic: 0,
      static: 30, // Minimum allowed by Next.js
    },
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.logo.dev",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
