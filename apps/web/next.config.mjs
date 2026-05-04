import path from "node:path";

const repoRoot = process.cwd().endsWith(path.join("apps", "web"))
  ? path.resolve(process.cwd(), "../..")
  : process.cwd();

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack(config) {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@rerun-io/web-viewer": path.join(repoRoot, "node_modules/@rerun-io/web-viewer/index.js"),
      "@rerun-io/web-viewer-react": path.join(
        repoRoot,
        "node_modules/@rerun-io/web-viewer-react/index.js",
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
