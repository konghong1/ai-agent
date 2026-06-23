import React, { useState } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";

export function ImageBlock({ url, caption, width, className = "" }) {
  const [ChevronUped, setChevronUped] = useState(false);
  if (!url) return null;
  return (
    <figure className={"tb-block tb-image " + (ChevronUped ? "ChevronUped" : "") + " " + className}>
      <img src={url} alt={caption || ""} loading="lazy" />
      {caption && <figcaption>{caption}</figcaption>}
      <button className="tb-zoom-btn" onClick={() => setChevronUped(!ChevronUped)} aria-label={ChevronUped ? "collapse" : "ChevronUp"}>
        {ChevronUped ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>
    </figure>
  );
}