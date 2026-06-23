import React from "react";
import { Sparkles } from "lucide-react";

export function CardBlock({ title, description, data, icon, status, className = "" }) {
  if (!title && !data) return null;
  return (
    <div className={"tb-block tb-card " + className}>
      <div className="tb-card-header">
        {icon ? <span className="tb-card-icon">{icon}</span> : <Sparkles size={14} className="tb-card-icon" />}
        {title && <h4 className="tb-card-title">{title}</h4>}
        {status && <span className={"tb-card-status tb-status-" + status}>{status}</span>}
      </div>
      {description && <p className="tb-card-desc">{description}</p>}
      {data && (
        <dl className="tb-card-data">
          {Object.entries(data).map(([key, val]) => (
            <div key={key} className="tb-data-row">
              <dt>{key}</dt>
              <dd>{typeof val === "number" ? val.toLocaleString() : String(val)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}