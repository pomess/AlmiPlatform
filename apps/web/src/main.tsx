import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// One-time migration: rename jarvis.* localStorage keys to kairos.*
// Safe to leave in permanently; it's a no-op once the map is empty.
(() => {
  try {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith("jarvis.")) {
        const newKey = "kairos." + k.slice("jarvis.".length);
        if (!localStorage.getItem(newKey)) {
          localStorage.setItem(newKey, localStorage.getItem(k) ?? "");
        }
        localStorage.removeItem(k);
      }
    }
  } catch { /* ignore */ }
})();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
