import { useRef, useState } from "react";
import { toast } from "sonner";
import { Images, X, Loader2 } from "lucide-react";
import { fileUrl, errMsg } from "@/lib/api";
import { uploadFile } from "@/lib/uploads";

export const GalleryUpload = ({ value = [], onChange, max = 8, testid = "gallery-upload" }) => {
  const input = useRef(null);
  const [pct, setPct] = useState(null);

  const pick = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    if (value.length + files.length > max) return toast.error(`Up to ${max} photos.`);
    let next = value.slice();  // running list — `value` stays stale inside this loop
    for (const file of files) {
      if (!file.type.startsWith("image/")) { toast.error(`${file.name} isn't an image.`); continue; }
      if (file.size > 5_000_000) { toast.error(`${file.name} is over 5MB.`); continue; }
      try {
        setPct(0);
        const data = await uploadFile(file, setPct);
        next = [...next, data.url].slice(0, max);
        onChange(next);
      } catch (er) { toast.error(er.message || errMsg(er)); }
    }
    setPct(null);
  };

  return (
    <div>
      <span className="text-xs font-bold text-slate-600">Gallery photos ({value.length}/{max})</span>
      <div className="mt-1.5 flex flex-wrap items-center gap-3">
        {value.map((url, i) => (
          <div key={url + i} className="relative" data-testid={`${testid}-item-${i}`}>
            <img src={fileUrl(url)} alt="" loading="lazy"
              className="h-20 w-28 rounded-xl object-cover border border-slate-200" />
            <button type="button" onClick={() => onChange(value.filter((v) => v !== url))}
              data-testid={`${testid}-remove-${i}`}
              className="absolute -top-2 -right-2 h-6 w-6 rounded-full bg-slate-900 text-white grid place-items-center">
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <input ref={input} type="file" accept="image/*" multiple onChange={pick} className="hidden" data-testid={testid} />
        <button type="button" onClick={() => input.current?.click()} disabled={pct !== null || value.length >= max}
          data-testid={`${testid}-btn`}
          className="h-20 w-28 rounded-xl border-2 border-dashed border-slate-300 grid place-items-center text-slate-400 transition-colors hover:border-brand-magenta hover:text-brand-magenta disabled:opacity-50">
          {pct !== null ? (
            <span className="flex flex-col items-center gap-1 text-[11px] font-bold">
              <Loader2 className="h-4 w-4 animate-spin" />{pct}%
            </span>
          ) : (
            <span className="flex flex-col items-center gap-1 text-[11px] font-bold"><Images className="h-5 w-5" />Add photos</span>
          )}
        </button>
      </div>
      <p className="text-[11px] text-slate-400 mt-1.5">JPG, PNG or WEBP · up to 5MB each · shown on the event page</p>
    </div>
  );
};
