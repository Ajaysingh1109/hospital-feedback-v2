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

// Register PWA Service Worker (Section 15)
if ("serviceWorker" in navigator && !window.location.host.includes("localhost:5173")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(
      (reg) => console.log("[PWA] Service Worker registered:", reg.scope),
      (err) => console.warn("[PWA] Service Worker registration failed:", err)
    );
  });
}

