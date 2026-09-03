/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: Caddy serves web/out from /srv/web (caddy/Dockerfile 2-stage build).
  output: 'export',
  images: {
    unoptimized: true,
  },
  // Skeleton has no ESLint config yet; type-checking still runs on build.
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
