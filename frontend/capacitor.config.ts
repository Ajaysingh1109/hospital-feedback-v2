import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.saarthi.feedbackmac",
  appName: "FEEDBACK MAC",
  webDir: "dist",
  server: {
    androidScheme: "https",
    cleartext: true, // Allows local LAN testing in development, HTTPS enforced in cloud
  },
  android: {
    allowMixedContent: true,
    captureInput: true,
    webContentsDebuggingEnabled: true,
  },
};

export default config;
