import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { Send, Flag, Trash2, ArrowLeft } from "lucide-react";

export default function Messages() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const active = params.get("c");
  const [convos, setConvos] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const endRef = useRef(null);

  const loadConvos = useCallback(() => {
    api.get("/conversations").then(({ data }) => setConvos(data.items)).catch(() => setConvos([]));
  }, []);

  const loadMsgs = useCallback(() => {
    if (!active) return;
    api.get(`/conversations/${active}/messages`).then(({ data }) => setMsgs(data.items)).catch((e) => toast.error(errMsg(e)));
  }, [active]);

  useEffect(() => { loadConvos(); }, [loadConvos]);
  useEffect(() => { loadMsgs(); }, [loadMsgs]);
  useEffect(() => {
    const t = setInterval(() => { loadMsgs(); loadConvos(); }, 5000);
    return () => clearInterval(t);
  }, [loadMsgs, loadConvos]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const body = text;
    setText("");
    try { await api.post(`/conversations/${active}/messages`, { body }); loadMsgs(); loadConvos(); }
    catch (er) { toast.error(errMsg(er)); }
  };

  const del = async () => {
    try { await api.delete(`/conversations/${active}`); toast.success("Conversation deleted"); setParams({}); loadConvos(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const report = async () => {
    try { await api.post("/reports", { target_type: "conversation", target_id: active, reason: "Reported conversation", details: "" });
      toast.success("Conversation reported to our safety team."); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!convos) return <Spinner />;
  const current = convos.find((c) => c.id === active);

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 pb-28" data-testid="messages-page">
      <SEO title="Messages" />
      <h1 className="text-3xl font-bold mb-6">Messages</h1>
      <div className="grid md:grid-cols-3 gap-5 rounded-2xl border border-slate-200 bg-white overflow-hidden min-h-[60vh]">
        <div className={`border-r border-slate-200 ${active ? "hidden md:block" : ""}`} data-testid="conversation-list">
          {convos.length ? convos.map((c) => (
            <button key={c.id} onClick={() => setParams({ c: c.id })} data-testid={`conversation-${c.id}`}
              className={`w-full text-left px-4 py-4 border-b border-slate-100 hover:bg-slate-50 ${active === c.id ? "bg-slate-50" : ""}`}>
              <div className="flex items-center gap-3">
                {c.avatar ? <img src={c.avatar} alt="" className="h-10 w-10 rounded-full object-cover" />
                  : <span className="h-10 w-10 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{c.title?.[0]}</span>}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-sm truncate">{c.title}</p>
                    {c.unread > 0 && <span className="h-5 min-w-5 px-1 rounded-full bg-slate-900 text-white text-[10px] grid place-items-center font-bold">{c.unread}</span>}
                  </div>
                  <p className="text-xs text-slate-500 truncate mt-0.5">{c.last_message || "Say hello"}</p>
                </div>
              </div>
            </button>
          )) : (
            <div className="p-8">
              <Empty title="No conversations" sub="Message a member from their profile to start chatting."
                action={<Link to="/discover" className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Find companions</Link>} />
            </div>
          )}
        </div>

        <div className={`md:col-span-2 flex flex-col ${active ? "" : "hidden md:flex"}`}>
          {active && current ? (
            <>
              <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200">
                <button onClick={() => setParams({})} className="md:hidden p-1" data-testid="chat-back"><ArrowLeft className="h-5 w-5" /></button>
                {current.other_id ? <Link to={`/u/${current.other_id}`} className="font-semibold text-sm" data-testid="chat-title">{current.title}</Link>
                  : <p className="font-semibold text-sm">{current.title}</p>}
                <div className="ml-auto flex gap-1">
                  <button onClick={report} data-testid="report-conversation" className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"><Flag className="h-4 w-4" /></button>
                  <button onClick={del} data-testid="delete-conversation" className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[55vh]" data-testid="message-thread">
                {msgs.map((m) => {
                  const mine = m.sender_id === user.id;
                  return (
                    <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${mine ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
                        <p className="text-sm whitespace-pre-wrap break-words">{m.body}</p>
                        <p className={`text-[10px] mt-1 ${mine ? "text-slate-400" : "text-slate-500"}`}>
                          {new Date(m.created_at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}
                          {mine && (m.read ? " · Read" : " · Sent")}
                        </p>
                      </div>
                    </div>
                  );
                })}
                <div ref={endRef} />
              </div>
              <form onSubmit={send} className="border-t border-slate-200 p-3 flex gap-2">
                <input data-testid="message-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a message…"
                  className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
                <button data-testid="send-message-btn" className="rounded-full bg-slate-900 text-white h-10 w-10 grid place-items-center"><Send className="h-4 w-4" /></button>
              </form>
            </>
          ) : (
            <div className="flex-1 grid place-items-center p-10 text-center">
              <p className="text-sm text-slate-500">Select a conversation to start chatting.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
