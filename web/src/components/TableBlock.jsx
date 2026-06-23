import React from "react";

export function TableBlock({ columns, rows, className = "" }) {
  if (!columns || !rows) return null;
  return (
    <div className={"tb-block tb-table " + className}>
      <table>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th key={i}>{typeof col === "string" ? col : (col.label || col.key)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {(Array.isArray(row) ? row : columns.map(c => row[c.key || c])).map((cell, ci) => (
                <td key={ci}>{cell ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}