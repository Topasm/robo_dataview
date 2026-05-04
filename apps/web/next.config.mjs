import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack(config) {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@rerun-io/web-viewer": fileURLToPath(import.meta.resolve("@rerun-io/web-viewer")),
      "@rerun-io/web-viewer-react": fileURLToPath(
        import.meta.resolve("@rerun-io/web-viewer-react"),
      )
    };
    config.experiments = {
      ...config.experiments,
      asyncWebAssembly: true,
      topLevelAwait: true
    };
    return config;
  }
};

export default nextConfig;
