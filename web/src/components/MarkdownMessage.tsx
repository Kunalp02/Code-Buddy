import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  content: string;
  onCodeRefClick?: (path: string, line?: number) => void;
}

const CODE_REF = /(`?)([\w./-]+\.(?:py|ts|tsx|js|jsx|go|java|rs|rb|php|cs|cpp|h|yaml|yml|json|md)):(\d+)(`?)/g;

function linkifyCodeRefs(text: string): string {
  return text.replace(CODE_REF, (_match, _q1, path, line) => `[${path}:${line}](code://${path}:${line})`);
}

export default function MarkdownMessage({ content, onCodeRefClick }: Props) {
  const prepared = linkifyCodeRefs(content);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            if (href?.startsWith("code://")) {
              const rest = href.replace("code://", "");
              const [path, lineStr] = rest.split(":");
              const line = lineStr ? parseInt(lineStr, 10) : undefined;
              return (
                <button
                  type="button"
                  className="md-code-ref"
                  onClick={() => onCodeRefClick?.(path, line)}
                >
                  {children}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
          code({ className, children }) {
            const isBlock = className?.includes("language-");
            if (isBlock) {
              return <code className={className}>{children}</code>;
            }
            return <code className="md-inline-code">{children}</code>;
          },
          pre({ children }) {
            return <pre className="md-pre">{children}</pre>;
          },
          table({ children }) {
            return (
              <div className="md-table-wrap">
                <table>{children}</table>
              </div>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
}
