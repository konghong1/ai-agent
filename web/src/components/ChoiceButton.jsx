import React from "react";

export function ChoiceButton({ label, value, onClick }) {
  return (
    <button
      className="choice-btn"
      onClick={() => onClick(value, label)}
      type="button"
    >
      {label}
    </button>
  );
}
