/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 同源代理:浏览器请求 /api/* 由 Next 服务器转发到 FastAPI。
  // 这样 session cookie 是同源 cookie(HttpOnly + SameSite=Lax 直接生效),
  // 避免跨端口 cookie 的 CORS/SameSite 问题。
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
