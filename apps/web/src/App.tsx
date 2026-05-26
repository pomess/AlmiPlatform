import { Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { Cockpit } from "./pages/Cockpit";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app/*" element={<Cockpit />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
