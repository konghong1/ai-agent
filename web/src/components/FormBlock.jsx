import React, { useState } from "react";

export function FormBlock({ fields, onSubmitLabel, className = "" }) {
  const [values, setValues] = useState({});
  const [submitted, setSubmitted] = useState(false);

  if (!fields || fields.length === 0) return null;

  const handleChange = (name, val) => {
    setValues((prev) => ({ ...prev, [name]: val }));
  };

  const handleSubmit = () => {
    setSubmitted(true);
    setTimeout(() => setSubmitted(false), 3000);
  };

  return (
    <div className={"tb-block tb-form " + className}>
      <div className="tb-form-fields">
        {fields.map((field) => {
          if (field.type === "select") {
            return (
              <div key={field.name} className="tb-field">
                <label>{field.label || field.name}</label>
                <select
                  defaultValue={values[field.name] || field.options?.[0]?.value || ""}
                  onChange={(e) => handleChange(field.name, e.target.value)}
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label || opt.value}</option>
                  ))}
                </select>
              </div>
            );
          }
          if (field.type === "checkbox") {
            return (
              <div key={field.name} className="tb-field tb-checkbox">
                <label>
                  <input
                    type="checkbox"
                    checked={!!values[field.name]}
                    onChange={(e) => handleChange(field.name, e.target.checked)}
                  />
                  {field.label || field.name}
                </label>
              </div>
            );
          }
          return (
            <div key={field.name} className="tb-field">
              <label>{field.label || field.name}</label>
              <input
                type={field.type || "text"}
                placeholder={field.placeholder || ""}
                onChange={(e) => handleChange(field.name, e.target.value)}
              />
            </div>
          );
        })}
      </div>
      <button className="tb-submit-btn" onClick={handleSubmit} disabled={submitted}>
        {submitted ? "Submitted" : (onSubmitLabel || "Submit")}
      </button>
    </div>
  );
}