import { fileURLToPath } from "node:url";

const rerunWebViewerPath = fileURLToPath(import.meta.resolve("@rerun-io/web-viewer"));
const rerunWebViewerReactPath = fileURLToPath(
  import.meta.resolve("@rerun-io/web-viewer-react"),
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Turbopack handles top-level await and async WASM natively, and its module
  // resolution does not need the absolute-path alias the webpack build uses
  // for the rerun viewer (Turbopack rejects absolute paths as "server
  // relative"). The minimal stub keeps the explicit `next dev --turbo` opt-in
  // working without surfacing a "webpack configured but turbopack is not"
  // warning.
  turbopack: {},
  webpack(config) {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@rerun-io/web-viewer": rerunWebViewerPath,
      "@rerun-io/web-viewer-react": rerunWebViewerReactPath
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
