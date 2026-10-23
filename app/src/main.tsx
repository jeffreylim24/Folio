import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { applyTheme, savedTheme } from "./theme";

// Before the first paint, so a saved theme never flashes the other one.
applyTheme(savedTheme());

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
