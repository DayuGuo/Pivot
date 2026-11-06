import { existsSync } from "node:fs";

// Opt-in for Linux test hosts whose shared GPU cannot allocate a WebKit context.
// Keep this in the browser child process; never change the app or global driver.
export function webkitLaunchOptions(environment = process.env) {
  if (environment.PIVOT_WEBKIT_SOFTWARE_RENDERING !== "1") return {};
  if (process.platform !== "linux") throw new Error("Software WebKit verification requires Linux.");
  const vendor = "/usr/share/glvnd/egl_vendor.d/50_mesa.json";
  if (!existsSync(vendor)) throw new Error("Software WebKit verification requires the Mesa EGL vendor installed by Playwright host dependencies.");
  return { env: { ...environment, LIBGL_ALWAYS_SOFTWARE: "true", GALLIUM_DRIVER: "llvmpipe", __EGL_VENDOR_LIBRARY_FILENAMES: vendor } };
}
