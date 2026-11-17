import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles.css";

const rootEl = document.getElementById("root");
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

// Register PWA Service Worker in production only (avoids development cache issues)
const isDevHost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
if ("serviceWorker" in navigator && !isDevHost) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(
      (reg) => console.log("[PWA] Service Worker registered:", reg.scope),
      (err) => console.warn("[PWA] Service Worker registration failed:", err)
    );
  });
}

