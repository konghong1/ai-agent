import React from "react";

export function TextBlock({ content, className = "" }) {
  if (!content) return null;
  return <div className={"tb-block tb-text " + className}>{content}</div>;
}