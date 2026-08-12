import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { Send, Flag, Trash2, ArrowLeft, Users } from "lucide-react";

const WS_URL = () => {
  const base = process.env.REACT_APP_BACKEND_URL.replace(/^http/, "ws");
  return `${base}/api/ws?token=${encodeURIComponent(localStorage.getItem("bud_token") || "")}`;
};

export default function Messages() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const active = params.get("c");
  const [convos, setConvos] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [online, setOnline] = useState([]);
  const [typing, setTyping] = useState(null);
  const [connected, setConnected] = useState(false);
  const endRef = useRef(null);
  const threadRef = useRef(null);
  const ws = useRef(null);
  const activeRef = useRef(active);
  const typingTimer = useRef(null);

  useEffect(() => { activeRef.current = active; }, [active]);

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
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs.length, typing]);

  // realtime socket
  useEffect(() => {
    let closed = false;
    let retry;
    const connect = () => {
      const socket = new WebSocket(WS_URL());
      ws.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 3000);
      };
      socket.onmessage = (e) => {
        const d = JSON.parse(e.data);
        if (d.type === "ready") setOnline(d.online || []);
        if (d.type === "presence") {
          setOnline((p) => (d.online ? [...new Set([...p, d.user_id])] : p.filter((x) => x !== d.user_id)));
        }
        if (d.type === "message") {
          if (d.conversation_id === activeRef.current) {
            setMsgs((p) => (p.some((m) => m.id === d.message.id) ? p : [...p, d.message]));
            if (d.message.sender_id !== user.id) api.get(`/conversations/${d.conversation_id}/messages`).catch(() => {});
          }
          setTyping(null);
          loadConvos();
        }
        if (d.type === "typing" && d.conversation_id === activeRef.current) setTyping(d.user_id);
        if (d.type === "stop_typing") setTyping(null);
        if (d.type === "read" && d.conversation_id === activeRef.current) {
          setMsgs((p) => p.map((m) => (m.sender_id === user.id ? { ...m, read: true } : m)));
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); ws.current?.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const emit = (type) => {
    if (ws.current?.readyState === 1 && active) ws.current.send(JSON.stringify({ type, conversation_id: active }));
  };

  const onType = (v) => {
    setText(v);
    emit("typing");
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => emit("stop_typing"), 1800);
  };

  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const body = text;
    setText("");
    emit("stop_typing");
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
  const isOnline = current?.other_id && online.includes(current.other_id);

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 pb-28" data-testid="messages-page">
      <SEO title="Messages" />
      <div className="flex items-center gap-3 mb-6">
        <h1 className="text-3xl font-bold">Messages</h1>
        <span data-testid="ws-status" className={`text-xs font-bold px-2.5 py-1 rounded-full ${connected ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
          {connected ? "Live" : "Reconnecting…"}
        </span>
      </div>
      <div className="grid md:grid-cols-3 gap-5 rounded-2xl border border-slate-200 bg-white overflow-hidden min-h-[60vh]">
        <div className={`border-r border-slate-200 ${active ? "hidden md:block" : ""}`} data-testid="conversation-list">
          {convos.length ? convos.map((c) => (
            <button key={c.id} onClick={() => setParams({ c: c.id })} data-testid={`conversation-${c.id}`}
              className={`w-full text-left px-4 py-4 border-b border-slate-100 hover:bg-slate-50 ${active === c.id ? "bg-slate-50" : ""}`}>
              <div className="flex items-center gap-3">
                <span className="relative">
                  {c.type === "event" ? (
                    <span className="h-10 w-10 rounded-full bg-slate-900 text-white grid place-items-center"><Users className="h-4 w-4" /></span>
                  ) : c.avatar ? <img src={c.avatar} alt="" className="h-10 w-10 rounded-full object-cover" />
                    : <span className="h-10 w-10 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{c.title?.[0]}</span>}
                  {c.other_id && online.includes(c.other_id) && <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full bg-emerald-500 border-2 border-white" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-semibold text-sm truncate">{c.title}{c.type === "event" && <span className="text-slate-400 font-normal"> · group</span>}</p>
                    {c.unread > 0 && <span className="h-5 min-w-5 px-1 rounded-full bg-slate-900 text-white text-[10px] grid place-items-center font-bold">{c.unread}</span>}
                  </div>
                  <p className="text-xs text-slate-500 truncate mt-0.5">{c.last_message || "Say hello"}</p>
                </div>
              </div>
            </button>
          )) : (
            <div className="p-8">
              <Empty title="No conversations" sub="Message a member from their profile, or buy an event pass to join its group chat."
                action={<Link to="/discover" className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Find companions</Link>} />
            </div>
          )}
        </div>

        <div className={`md:col-span-2 flex flex-col ${active ? "" : "hidden md:flex"}`}>
          {active && current ? (
            <>
              <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200">
                <button onClick={() => setParams({})} className="md:hidden p-1" data-testid="chat-back"><ArrowLeft className="h-5 w-5" /></button>
                <div>
                  {current.other_id ? <Link to={`/u/${current.other_id}`} className="font-semibold text-sm" data-testid="chat-title">{current.title}</Link>
                    : <p className="font-semibold text-sm" data-testid="chat-title">{current.title}</p>}
                  <p className="text-[11px] text-slate-500" data-testid="chat-presence">
                    {current.type === "event" ? `${current.members?.length || 0} ticket holders` : isOnline ? "Online now" : "Offline"}
                  </p>
                </div>
                <div className="ml-auto flex gap-1">
                  <button onClick={report} data-testid="report-conversation" className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"><Flag className="h-4 w-4" /></button>
                  <button onClick={del} data-testid="delete-conversation" className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
              <div ref={threadRef} className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[55vh]" data-testid="message-thread">
                {msgs.map((m) => {
                  const mine = m.sender_id === user.id;
                  return (
                    <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${mine ? "bg-slate-900 text-white" : "bg-slate-100"}`}>
                        {!mine && current.type === "event" && <p className="text-[11px] font-bold text-slate-500 mb-0.5">{m.sender_name}</p>}
                        <p className="text-sm whitespace-pre-wrap break-words">{m.body}</p>
                        <p className={`text-[10px] mt-1 ${mine ? "text-slate-400" : "text-slate-500"}`}>
                          {new Date(m.created_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                          {mine && (m.read ? " · Read" : " · Sent")}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {typing && (
                  <div className="flex justify-start" data-testid="typing-indicator">
                    <div className="rounded-2xl bg-slate-100 px-4 py-3 flex gap-1">
                      {[0, 150, 300].map((d) => (
                        <span key={d} className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: `${d}ms` }} />
                      ))}
                    </div>
                  </div>
                )}
                <div ref={endRef} />
              </div>
              <form onSubmit={send} className="border-t border-slate-200 p-3 flex gap-2">
                <input data-testid="message-input" value={text} onChange={(e) => onType(e.target.value)} placeholder="Write a message…"
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
