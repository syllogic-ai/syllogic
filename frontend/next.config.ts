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
    // Profile photo and CSV flows submit larger payloads via server actions.
    serverActions: {
      // Keep comfortably above the 10MB client-side CSV limit to account for
      // multipart/serialization overhead.
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
