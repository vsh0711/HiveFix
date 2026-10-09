/** @type {import('next').NextConfig} */
const nextConfig = {
  // Lean production image: next.config's own standalone server + only the deps
  // it actually traced, instead of shipping the full node_modules tree.
  output: "standalone",
};

module.exports = nextConfig;
