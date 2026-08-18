import { useEffect, useRef } from "react";
import { Bold, Italic, Underline, List, ListOrdered, Link2, Quote, Heading2, Heading3, Eraser } from "lucide-react";

const BUTTONS = [
  ["bold", Bold, "Bold"],
  ["italic", Italic, "Italic"],
  ["underline", Underline, "Underline"],
  ["h2", Heading2, "Heading"],
  ["h3", Heading3, "Sub-heading"],
  ["ul", List, "Bullet list"],
  ["ol", ListOrdered, "Numbered list"],
  ["quote", Quote, "Quote"],
  ["link", Link2, "Link"],
  ["clear", Eraser, "Clear formatting"],
];

const run = (key) => {
  if (key === "h2") return document.execCommand("formatBlock", false, "h2");
  if (key === "h3") return document.execCommand("formatBlock", false, "h3");
  if (key === "quote") return document.execCommand("formatBlock", false, "blockquote");
  if (key === "ul") return document.execCommand("insertUnorderedList");
  if (key === "ol") return document.execCommand("insertOrderedList");
  if (key === "clear") return document.execCommand("removeFormat");
  if (key === "link") {
    const url = window.prompt("Link to (https://… or /path)");
    if (url) document.execCommand("createLink", false, url);
    return;
  }
  document.execCommand(key);
};

/** Formatting-friendly replacement for plain textareas on any content members or admins will read. */
export const RichText = ({ value = "", onChange, rows = 8, testid = "richtext", placeholder = "" }) => {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== (value || "")) ref.current.innerHTML = value || "";
  }, [value]);

  const emit = () => onChange?.(ref.current?.innerHTML || "");

  return (
    <div className="rounded-xl border border-slate-200 bg-white" data-testid={`${testid}-wrap`}>
      <div className="flex flex-wrap gap-1 border-b border-slate-100 px-2 py-1.5">
        {BUTTONS.map(([key, Icon, label]) => (
          <button key={key} type="button" title={label} aria-label={label}
            data-testid={`${testid}-${key}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => { run(key); emit(); }}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900">
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>
      <div ref={ref} contentEditable suppressContentEditableWarning data-testid={testid}
        onInput={emit} onBlur={emit} data-placeholder={placeholder}
        style={{ minHeight: `${rows * 22 + 16}px` }}
        className="prose-editor max-w-none px-3.5 py-3 text-sm leading-relaxed outline-none" />
    </div>
  );
};

/** Renders admin/member authored HTML that the backend has already sanitised. */
export const RichHtml = ({ html = "", className = "", testid }) => (
  <div data-testid={testid} className={`rich-html ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
);
