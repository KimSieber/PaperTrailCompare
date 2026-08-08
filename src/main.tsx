/**
 * @file    src/main.tsx
 * @purpose Application entry point. Mounts the React root component into
 *          the Tauri WebView DOM.
 * @author  Kim Sieber
 * @created YYYY-MM-DD
 * @changed 2026-08-09
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
