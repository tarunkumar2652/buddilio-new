import { useRef, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, fileUrl } from "@/lib/api";
import { Upload, X } from "lucide-react";

export const ImageUpload = ({ value, onChange, label = "Image", testid = "image-upload", aspect = "square" }) => {
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  const pick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5_000_000) return toast.error("Please pick an image under 5MB.");
    const form = new FormData();
    form.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post("/uploads", form, { headers: { "Content-Type": "multipart/form-data" } });
      onChange(data.url);
      toast.success("Image uploaded");
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <div>
      <span className="text-xs font-bold text-slate-600">{label}</span>
      <div className="mt-1.5 flex items-center gap-4">
        {value ? (
          <div className="relative">
            <img src={fileUrl(value)} alt="" loading="lazy"
              className={`${aspect === "wide" ? "h-20 w-32" : "h-20 w-20"} rounded-xl object-cover border border-slate-200`} />
            <button type="button" onClick={() => onChange("")} data-testid={`${testid}-clear`}
              className="absolute -top-2 -right-2 h-6 w-6 rounded-full bg-slate-900 text-white grid place-items-center">
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <div className={`${aspect === "wide" ? "h-20 w-32" : "h-20 w-20"} rounded-xl bg-slate-100 grid place-items-center text-slate-400`}>
            <Upload className="h-5 w-5" />
          </div>
        )}
        <div>
          <input ref={input} type="file" accept="image/*" onChange={pick} className="hidden" data-testid={testid} />
          <button type="button" onClick={() => input.current?.click()} disabled={busy} data-testid={`${testid}-btn`}
            className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-xs font-bold disabled:opacity-60">
            {busy ? "Uploading…" : value ? "Replace image" : "Upload image"}
          </button>
          <p className="text-[11px] text-slate-400 mt-1.5">JPG, PNG or WEBP · up to 5MB</p>
        </div>
      </div>
    </div>
  );
};
