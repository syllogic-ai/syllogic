import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for production Docker images (small runtime image).
  output: "standalone",
  experimental: {
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
    serverActions: {
      bodySizeLimit: "25mb",
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
