import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { TaskPanel } from "@/components/explore/TaskPanel";

/** Explore moved into the assistant. This address stays for the browser agent's run view (?task=…) and old links. */
export default function ExplorePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const task = params.get("task");
  if (!task) return <Navigate to="/assistant" replace />;
  return <div className="h-full overflow-y-auto overscroll-contain"><TaskPanel id={task} onClose={() => navigate(-1)} /></div>;
}
