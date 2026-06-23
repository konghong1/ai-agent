import React, { useState } from "react";
import { Check, Copy } from "lucide-react";

const LANG_MAP = {
  js: "javascript", ts: "typescript", py: "python",
  jsx: "javascript", tsx: "typescript", sh: "bash",
};

export function CodeBlock({ code, lang, title, className = "" }) {
  const [copied, setCopied] = useState(false);
  if (!code) return null;
  const displayLang = LANG_MAP[lang] || lang || "text";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={"tb-block tb-code " + className}>
      {(title || displayLang !== "text") && (
        <div className="tb-code-header">
          <span className="tb-code-lang">{title || displayLang}</span>
        </div>
      )}
      <pre className="tb-code-pre"><code>{code}</code></pre>
      <button className="tb-copy-btn" onClick={handleCopy} aria-label="copy">
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}