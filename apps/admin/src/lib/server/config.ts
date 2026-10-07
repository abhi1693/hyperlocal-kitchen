import "server-only";
function origin(name: string, fallback: string) {
  const value = process.env[name] ?? (process.env.NODE_ENV !== "production" ? fallback : undefined);
  if (!value) throw new Error(`${name} is required`);
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  )
    throw new Error(`${name} must be an origin`);
  return url.origin;
}
export function adminApiOrigin() {
  return origin("KITCHEN_ADMIN_API_URL", "http://localhost:13001");
}
export function adminWebOrigin() {
  return origin("KITCHEN_ADMIN_BASE_URL", "http://localhost:3001");
}
