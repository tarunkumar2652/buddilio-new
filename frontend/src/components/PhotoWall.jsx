import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, Loader2, X } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";
import { uploadFile } from "@/lib/uploads";

export const PhotoWall = ({ eventId }) => {
  const [data, setData] = useState(null);
  const [pct, setPct] = useState(null);
  const [caption, setCaption] = useState("");
  const input = useRef(null);

  const load = useCallback(() => {
    api.get(`/events/${eventId}/photos`).then(({ data }) => setData(data)).catch(() => setData(null));
  }, [eventId]);
  useEffect(() => { load(); }, [load]);

  const pick = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    for (const file of files) {
      if (!file.type.startsWith("image/")) { toast.error(`${file.name} isn't an image.`); continue; }
      if (file.size > 5_000_000) { toast.error(`${file.name} is over 5MB.`); continue; }
      try {
        setPct(0);
        const up = await uploadFile(file, setPct);
        await api.post(`/events/${eventId}/photos`, { url: up.url, caption });
      } catch (er) { toast.error(er.response ? errMsg(er) : er.message); }
    }
    setPct(null); setCaption(""); load();
    toast.success("Added to the photo wall.");
  };

  const remove = async (id) => {
    try { await api.delete(`/events/${eventId}/photos/${id}`); load(); toast.success("Photo removed."); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return null;

  return (
    <div data-testid="photo-wall">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Photo wall</h2>
          <p className="mt-1 text-sm text-slate-500">
            {data.count > 0 ? `${data.count} photo${data.count === 1 ? "" : "s"} from the people who were there`
              : "Real photos from the crowd land here."}
          </p>
        </div>
        {data.can_post ? (
          <div className="flex items-center gap-2">
            <input value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption (optional)"
              data-testid="photo-wall-caption"
              className="rounded-full border border-slate-200 px-4 py-2 text-sm w-40 sm:w-56" />
            <input ref={input} type="file" accept="image/*" multiple onChange={pick} className="hidden"
              data-testid="photo-wall-input" />
            <button onClick={() => input.current?.click()} disabled={pct !== null}
              data-testid="photo-wall-upload-btn"
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5 disabled:opacity-50">
              {pct !== null ? <><Loader2 className="h-4 w-4 animate-spin" />{pct}%</>
                : <><Camera className="h-4 w-4" />Add photos</>}
            </button>
          </div>
        ) : data.reason ? (
          <p className="text-xs font-semibold text-slate-400" data-testid="photo-wall-reason">{data.reason}</p>
        ) : null}
      </div>

      {data.items.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400"
          data-testid="photo-wall-empty">No photos yet — be the first to show the vibe.</p>
      ) : (
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
          {data.items.map((p) => (
            <figure key={p.id} className="relative group" data-testid={`photo-wall-item-${p.id}`}>
              <img src={fileUrl(p.url)} alt={p.caption || "Event photo"} loading="lazy"
                className="rounded-2xl aspect-square object-cover w-full" />
              <figcaption className="absolute inset-x-0 bottom-0 rounded-b-2xl bg-gradient-to-t from-slate-900/85 to-transparent p-3 text-[11px] font-semibold text-white">
                {p.caption ? <span className="block line-clamp-2">{p.caption}</span> : null}
                <span className="text-white/70">{p.user_name}</span>
              </figcaption>
              {p.can_delete && (
                <button onClick={() => remove(p.id)} data-testid={`photo-wall-remove-${p.id}`}
                  className="absolute top-2 right-2 h-7 w-7 rounded-full bg-slate-900/80 text-white grid place-items-center opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </figure>
          ))}
        </div>
      )}
    </div>
  );
};
