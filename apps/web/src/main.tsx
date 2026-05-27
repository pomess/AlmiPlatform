import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// One-time migration: rename legacy localStorage prefixes to disease360.*
// Chain handles jarvis.* → disease360.* and kairos.* → disease360.* in one pass.
// Safe to leave in permanently; it's a no-op once the map is empty.
(() => {
  try {
    const PREFIXES = ["jarvis.", "disease360."];
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (!k) continue;
      const prefix = PREFIXES.find((p) => k.startsWith(p));
      if (!prefix) continue;
      const newKey = "disease360." + k.slice(prefix.length);
      if (!localStorage.getItem(newKey)) {
        localStorage.setItem(newKey, localStorage.getItem(k) ?? "");
      }
      localStorage.removeItem(k);
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
