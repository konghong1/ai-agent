import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { TextBlock } from "./TextBlock";
import { ImageBlock } from "./ImageBlock";
import { CardBlock } from "./CardBlock";
import { TableBlock } from "./TableBlock";
import { CodeBlock } from "./CodeBlock";
import { FormBlock } from "./FormBlock";
import { ChoiceButton } from "./ChoiceButton";

const BLOCK_COMPONENTS = {
  text: TextBlock,
  image: ImageBlock,
  card: CardBlock,
  table: TableBlock,
  code: CodeBlock,
  form: FormBlock,
};

export function MessageRenderer({ message, onChoiceClick }) {
  const blocks = message?.extra?.blocks;

  if (blocks && typeof blocks === "object" && Object.keys(blocks).length > 0) {
    const choices = blocks.choices;
    const hasChoices = Array.isArray(choices) && choices.length > 0;

    return (
      <div className="rich-message">
        {message.content && <TextBlock content={message.content} />}
        {hasChoices && (
          <div className="choice-group">
            {choices.map((choice, i) => (
              <ChoiceButton
                key={i}
                label={choice.label || choice.value || String(choice)}
                value={choice.value || String(choice)}
                onClick={onChoiceClick || (() => {})}
              />
            ))}
          </div>
        )}
        {Object.entries(blocks).map(([key, value]) => {
          if (key === "choices") return null;
          const blockType = typeof value === "object" ? value.type || key : key;
          const data = typeof value === "object" ? value : { content: value };
          const Component = BLOCK_COMPONENTS[blockType];
          if (!Component) return <TextBlock key={key} content={JSON.stringify(value)} />;
          return <Component key={key} {...data} />;
        })}
      </div>
    );
  }

  return (
    <div className="rich-message">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {processMarkdown(message.content || "")}
      </ReactMarkdown>
    </div>
  );
}

function processMarkdown(text) {
  if (!text) return "";
  let parts = [];
  let lastIndex = 0;
  const customBlockRe = /:::(card|chart|form)\s+([^:]+):::/g;
  let match;

  while ((match = customBlockRe.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const blockType = match[1];
    const attrs = match[2];
    parts.push("%%" + blockType + ":" + attrs + "%%");
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  if (parts.length === 1) return text;
  return parts.join("");
}
