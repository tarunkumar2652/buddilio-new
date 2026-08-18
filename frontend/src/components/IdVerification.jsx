import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Upload } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { uploadFile } from "@/lib/uploads";
import { Badge } from "@/components/Shared";

export const IdVerification = () => {
  const [data, setData] = useState(null);
  const [docType, setDocType] = useState("passport");
  const [address, setAddress] = useState("");
  const [files, setFiles] = useState([]);
  const [pct, setPct] = useState(0);
  const [editing, setEditing] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    api.get("/me/verification").then(({ data }) => {
      setData(data);
      if (data.submission) {
        setDocType(data.submission.doc_type);
        setAddress(data.submission.address || "");
        setFiles(data.submission.documents || []);
      }
    }).catch(() => setData(false));
  }, []);

  const pick = async (e) => {
    const list = Array.from(e.target.files || []);
    for (const file of list.slice(0, 4 - files.length)) {
      try {
        const up = await uploadFile(file, setPct);
        setFiles((f) => [...f, { url: up.url, name: file.name }]);
      } catch (er) { toast.error(er.message || "Upload failed"); }
    }
    setPct(0);
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async () => {
    try {
      const { data: res } = await api.put("/me/verification", { doc_type: docType, documents: files, address });
      setData((d) => ({ ...d, submission: res.submission }));
      setEditing(false);
      toast.success("Sent for review — usually within a day.");
    } catch (e) { toast.error(errMsg(e)); }
  };

  const pickType = (value) => {
    setDocType(value);
    api.post("/me/verification/start", { doc_type: value }).catch(() => {});
  };

  if (!data) return null;
  const status = data.verified ? "verified" : data.submission?.status || "none";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="id-verification-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-bold"><ShieldCheck className="h-4 w-4" />ID & address verification</p>
        <Badge tone={status === "verified" ? "green" : status === "pending" ? "amber" : status === "rejected" ? "red" : "slate"}>
          <span data-testid="id-verification-status">{status === "none" ? "not started" : status}</span>
        </Badge>
      </div>
      <p className="mt-2 text-sm text-slate-500">
        Verified members get the badge, unlock hangout hosting and are trusted faster by organisers.
      </p>
      {data.submission?.note && <p className="mt-2 text-sm text-amber-700">{data.submission.note}</p>}

      {status !== "verified" || editing ? (
        <div className="mt-5 space-y-4">
          <label className="block"><span className="text-xs font-bold text-slate-600">Document type</span>
            <select value={docType} onChange={(e) => pickType(e.target.value)} data-testid="id-doc-type"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
              {data.types.map((t) => <option key={t.key} value={t.key}>{t.label} · proves {t.proves}</option>)}
            </select></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">Address on the document</span>
            <textarea rows={2} value={address} onChange={(e) => setAddress(e.target.value)} data-testid="id-address"
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>

          <div className="flex flex-wrap items-center gap-2" data-testid="id-files">
            {files.map((f, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold">
                {f.name}
                <button onClick={() => setFiles(files.filter((_, x) => x !== i))} data-testid={`id-file-remove-${i}`}
                  className="text-slate-400 hover:text-rose-600">×</button>
              </span>
            ))}
            {files.length < 4 && (
              <button onClick={() => inputRef.current?.click()} data-testid="id-file-pick"
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">
                <Upload className="h-3.5 w-3.5" />{pct ? `Uploading ${pct}%` : "Add file"}
              </button>
            )}
            <input ref={inputRef} type="file" accept="image/*,.pdf" multiple hidden onChange={pick} data-testid="id-file-input" />
          </div>

          <button onClick={submit} disabled={!files.length} data-testid="id-verification-submit"
            className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
            {data.submission ? "Resubmit for review" : "Send for review"}
          </button>
          <p className="text-[11px] text-slate-400">Passport, Aadhaar, driving licence, national ID, utility bill and more.
            Documents are visible only to our verification team.</p>
        </div>
      ) : (
        <button onClick={() => setEditing(true)} data-testid="id-verification-update"
          className="mt-4 rounded-full border border-slate-200 px-5 py-2.5 text-xs font-bold">
          Update my documents
        </button>
      )}
    </div>
  );
};
