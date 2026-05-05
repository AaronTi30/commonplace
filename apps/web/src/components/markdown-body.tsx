"use client";

import ReactMarkdown from "react-markdown";

type Props = {
  content: string;
  className?: string;
};

export function MarkdownBody({ content, className }: Props) {
  return (
    <div className={className ?? "text-[15px] leading-relaxed text-zinc-800"}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h2 className="mt-4 text-lg font-semibold text-zinc-900">{children}</h2>
          ),
          h2: ({ children }) => (
            <h3 className="mt-3 text-base font-semibold text-zinc-900">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="mt-2 text-sm font-semibold text-zinc-900">{children}</h4>
          ),
          p: ({ children }) => <p className="my-2">{children}</p>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-4 border-indigo-200 pl-4 text-zinc-700">
              {children}
            </blockquote>
          ),
          ul: ({ children }) => <ul className="my-2 list-disc pl-6">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal pl-6">{children}</ol>,
          li: ({ children }) => <li className="my-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          a: ({ href, children }) => (
            <a href={href} className="text-indigo-600 underline underline-offset-2">
              {children}
            </a>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
