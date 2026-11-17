import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Port 5173 is the Cognito callback origin and the API's CORS origin, so it must not drift.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  preview: { port: 5173, strictPort: true },
});
