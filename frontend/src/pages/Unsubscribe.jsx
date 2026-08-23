import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { MailX, Check } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { SEO } from "@/components/Shared";

export default function Unsubscribe() {
  const [params] = useSearchParams();
  const token = params.get("t") || "";
  const [state, setState] = useState("working");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) { setState("error"); setMsg("That link is missing its code."); return; }
    api.post("/newsletter/unsubscribe", { token })
      .then(({ data }) => { setState("done"); setMsg(data.message); })
      .catch((e) => { setState("error"); setMsg(errMsg(e)); });
  }, [token]);

  return (
    <div className="grid min-h-[70vh] place-items-center px-6" data-testid="unsubscribe-page">
      <SEO title="Unsubscribed" description="Journal email preferences" />
      <div className="max-w-md text-center">
        {state === "done" ? <Check className="mx-auto h-8 w-8 text-emerald-500" />
          : <MailX className="mx-auto h-8 w-8 text-slate-300" />}
        <h1 className="mt-4 font-display text-3xl font-bold text-slate-900">
          {state === "working" ? "One moment…" : state === "done" ? "You're unsubscribed" : "We couldn't do that"}
        </h1>
        <p className="mt-3 text-sm text-slate-500" data-testid="unsubscribe-message">{msg}</p>
        <Link to="/blog" data-testid="unsubscribe-back"
          className="mt-7 inline-block rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white">
          Back to the Journal
        </Link>
      </div>
    </div>
  );
}
