import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Dashboard from "./pages/Dashboard";
import Queue from "./pages/Queue";
import MonitorDetail from "./pages/MonitorDetail";
import MonitorListings from "./pages/MonitorListings";

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/monitor/:id" element={<MonitorDetail />} />
        <Route path="/monitor/:id/listings" element={<MonitorListings />} />
      </Routes>
    </BrowserRouter>
  );
}
