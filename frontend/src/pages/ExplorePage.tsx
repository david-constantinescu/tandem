import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { TaskPanel } from "@/components/explore/TaskPanel";

/** Explorarea s-a mutat in asistent. Adresa ramane pentru vederea de rulare a agentului de browser (?task=...) si pentru linkuri vechi */
export default function ExplorePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const task = params.get("task");
  if (!task) return <Navigate to="/assistant" replace />;
  return <div className="h-full overflow-y-auto overscroll-contain"><TaskPanel id={task} onClose={() => navigate(-1)} /></div>;
}
