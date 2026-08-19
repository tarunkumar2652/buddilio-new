import { useEffect, useState } from "react";
import { toast } from "sonner";
import { X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { ImageUpload } from "@/components/ImageUpload";
import { RichText } from "@/components/RichText";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const L = ({ label, children, hint }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

const Modal = ({ title, onClose, children, testid }) => (
  <div className="fixed inset-0 z-[80] grid place-items-start overflow-y-auto bg-slate-900/60 p-4 sm:p-8" data-testid={testid}>
    <div className="mx-auto w-full max-w-2xl rounded-2xl bg-white p-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold">{title}</h3>
        <button onClick={onClose} data-testid={`${testid}-close`} className="rounded-full border border-slate-200 p-2"><X className="h-4 w-4" /></button>
      </div>
      <div className="mt-5">{children}</div>
    </div>
  </div>
);

const PROFILE_BLANK = {
  full_name: "", email: "", role: "user", password: "", city: "", country: "", age: 25, bio: "",
  photo: "", mobile: "", org_name: "", interests: [], status: "active", verified: false,
};

export const ProfileForm = ({ profile, onClose, onSaved }) => {
  const [f, setF] = useState({ ...PROFILE_BLANK, ...(profile || {}) });
  const [busy, setBusy] = useState(false);
  const editing = !!profile?.id;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...f, age: Number(f.age) || 25, interests: f.interests || [] };
      if (editing) await api.put(`/admin/users/${profile.id}`, body);
      else await api.post("/admin/users", body);
      toast.success(editing ? "Profile updated." : "Profile created — they'll get an email to set a password.");
      onSaved(); onClose();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <Modal title={editing ? `Edit ${profile.full_name}` : "New profile"} onClose={onClose} testid="profile-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <L label="Full name"><input required value={f.full_name} data-testid="profile-name"
            onChange={(e) => setF({ ...f, full_name: e.target.value })} className={cls} /></L>
          <L label="Email"><input required type="email" value={f.email} data-testid="profile-email"
            onChange={(e) => setF({ ...f, email: e.target.value })} className={cls} /></L>
          <L label="Role"><select value={f.role} data-testid="profile-role"
            onChange={(e) => setF({ ...f, role: e.target.value })} className={cls}>
            {["user", "partner", "manager", "admin"].map((r) => <option key={r} value={r}>{r}</option>)}
          </select></L>
          <L label="Status"><select value={f.status} data-testid="profile-status"
            onChange={(e) => setF({ ...f, status: e.target.value })} className={cls}>
            {["active", "suspended", "banned", "pending", "deleted"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select></L>
          <L label="City"><input value={f.city} data-testid="profile-city"
            onChange={(e) => setF({ ...f, city: e.target.value })} className={cls} /></L>
          <L label="Country"><input value={f.country || ""} data-testid="profile-country"
            onChange={(e) => setF({ ...f, country: e.target.value })} className={cls} /></L>
          <L label="Age"><input type="number" min={21} value={f.age} data-testid="profile-age"
            onChange={(e) => setF({ ...f, age: e.target.value })} className={cls} /></L>
          <L label="Mobile"><input value={f.mobile || ""} data-testid="profile-mobile"
            onChange={(e) => setF({ ...f, mobile: e.target.value })} className={cls} /></L>
          {f.role === "partner" && (
            <L label="Organisation name"><input value={f.org_name || ""} data-testid="profile-org"
              onChange={(e) => setF({ ...f, org_name: e.target.value })} className={cls} /></L>
          )}
          <L label={editing ? "New password (optional)" : "Password (blank = email invite)"}>
            <input type="text" value={f.password || ""} data-testid="profile-password"
              onChange={(e) => setF({ ...f, password: e.target.value })} className={cls} />
          </L>
        </div>
        <L label="Bio"><RichText value={f.bio || ""} rows={4} testid="profile-bio"
          onChange={(html) => setF({ ...f, bio: html })} /></L>
        <L label="Interests (comma separated)">
          <input value={(f.interests || []).join(", ")} data-testid="profile-interests"
            onChange={(e) => setF({ ...f, interests: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
            className={cls} />
        </L>
        <ImageUpload value={f.photo} onChange={(url) => setF({ ...f, photo: url })} label="Profile photo" testid="profile-photo" />
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={!!f.verified} data-testid="profile-verified"
            onChange={(e) => setF({ ...f, verified: e.target.checked })} />Verified badge
        </label>
        <button disabled={busy} data-testid="profile-save"
          className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : editing ? "Save profile" : "Create profile"}
        </button>
      </form>
    </Modal>
  );
};

const EVENT_BLANK = {
  title: "", description: "", category: "Nightlife", city: "", country: "", venue: "", starts_at: "",
  ends_at: "", cover_image: "", price: 0, price_currency: "INR", capacity: 50, rules: "", cancellation_policy: "",
  approval_mode: "instant", featured: false, partner_id: "", status: "published",
};

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "JPY", "AUD", "THB"];

export const EventForm = ({ event, onClose, onSaved }) => {
  const [f, setF] = useState({
    ...EVENT_BLANK,
    ...(event || {}),
    // The event carries a converted base price; the organiser's own figure lives in price_input.
    price: event ? (event.price_input ?? event.price ?? 0) : 0,
    price_currency: event?.price_currency || "INR",
  });
  const [hosts, setHosts] = useState([]);
  const [busy, setBusy] = useState(false);
  const editing = !!event?.id;

  useEffect(() => {
    api.get("/hosts", { params: { limit: 50 } }).then(({ data }) => setHosts(data.items)).catch(() => setHosts([]));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { ...f, price: Number(f.price) || 0, capacity: Number(f.capacity) || 1 };
      if (editing) await api.put(`/admin/events/${event.id}`, body);
      else await api.post("/admin/events", body);
      toast.success(editing ? "Event updated." : "Event created.");
      onSaved(); onClose();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <Modal title={editing ? `Edit ${event.title}` : "New event"} onClose={onClose} testid="event-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <L label="Title"><input required value={f.title} data-testid="event-title"
            onChange={(e) => setF({ ...f, title: e.target.value })} className={cls} /></L>
          <L label="Category"><input required value={f.category} data-testid="event-category"
            onChange={(e) => setF({ ...f, category: e.target.value })} className={cls} /></L>
          <L label="City"><input required value={f.city} data-testid="event-city"
            onChange={(e) => setF({ ...f, city: e.target.value })} className={cls} /></L>
          <L label="Venue"><input value={f.venue} data-testid="event-venue"
            onChange={(e) => setF({ ...f, venue: e.target.value })} className={cls} /></L>
          <L label="Starts at (ISO)"><input required value={f.starts_at} placeholder="2026-07-04T20:00:00Z"
            data-testid="event-starts" onChange={(e) => setF({ ...f, starts_at: e.target.value })} className={cls} /></L>
          <L label="Ends at (ISO)"><input value={f.ends_at || ""} data-testid="event-ends"
            onChange={(e) => setF({ ...f, ends_at: e.target.value })} className={cls} /></L>
          <L label="Price"><input type="number" min={0} step="any" value={f.price} data-testid="event-price"
            onChange={(e) => setF({ ...f, price: e.target.value })} className={cls} /></L>
          <L label="Priced in" hint="Locals pay exactly this amount; other currencies convert automatically.">
            <select value={f.price_currency} data-testid="event-price-currency"
              onChange={(e) => setF({ ...f, price_currency: e.target.value })} className={cls}>
              {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </L>
          <L label="Capacity"><input type="number" min={1} value={f.capacity} data-testid="event-capacity"
            onChange={(e) => setF({ ...f, capacity: e.target.value })} className={cls} /></L>
          <L label="Organiser"><select value={f.partner_id || ""} data-testid="event-host"
            onChange={(e) => setF({ ...f, partner_id: e.target.value })} className={cls}>
            <option value="">Buddilio (in-house)</option>
            {hosts.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
          </select></L>
          <L label="Status"><select value={f.status} data-testid="event-status"
            onChange={(e) => setF({ ...f, status: e.target.value })} className={cls}>
            {["published", "draft", "submitted", "rejected", "completed"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select></L>
        </div>
        <L label="Description"><RichText value={f.description} rows={5} testid="event-description"
          onChange={(html) => setF({ ...f, description: html })} /></L>
        <L label="Rules"><RichText value={f.rules || ""} rows={3} testid="event-rules"
          onChange={(html) => setF({ ...f, rules: html })} /></L>
        <L label="Cancellation policy"><RichText value={f.cancellation_policy || ""} rows={3} testid="event-cancellation"
          onChange={(html) => setF({ ...f, cancellation_policy: html })} /></L>
        <ImageUpload value={f.cover_image} onChange={(url) => setF({ ...f, cover_image: url })}
          label="Cover image" testid="event-cover" aspect="wide" />
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={!!f.featured} data-testid="event-featured"
            onChange={(e) => setF({ ...f, featured: e.target.checked })} />Feature on the homepage
        </label>
        <button disabled={busy} data-testid="event-save"
          className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : editing ? "Save event" : "Create event"}
        </button>
      </form>
    </Modal>
  );
};
