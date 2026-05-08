import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';
import { Message } from '@/hooks/useAriaSocket';
import { ReactNode, useEffect, useRef, useState, useCallback } from 'react';
import { Copy01Icon as Copy, Tick01Icon as Check, Refresh01Icon as RefreshCw, PencilIcon as Pencil, Alert02Icon as AlertTriangle, ReloadIcon as RotateCcw } from 'hugeicons-react';

// ---- Extract raw text from React children tree ----
function extractText(node: ReactNode): string {
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (typeof node === 'object' && node && 'props' in node) {
    const props = node.props as { children?: ReactNode };
    if (props.children) return extractText(props.children);
  }
  return '';
}

// ---- Code block with copy button ----
function CodeBlock({ children, className, ...props }: React.HTMLAttributes<HTMLPreElement>) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const text = extractText(children).replace(/\n$/, '');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group">
      <pre className={className} {...props}>
        {children}
      </pre>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-secondary/80 hover:bg-gray-300 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
        title="Copy code"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}

// ---- Editable user message ----
function UserMessage({ msg, onEdit }: { msg: Message, onEdit?: (id: string, text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(msg.text);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.setSelectionRange(editText.length, editText.length);
    }
  }, [editing, editText.length]);

  if (editing) {
    return (
      <div className="flex flex-col gap-2 bg-sidebar px-5 py-3 rounded-2xl rounded-tr-sm">
        <textarea
          ref={inputRef}
          value={editText}
          onChange={e => setEditText(e.target.value)}
          className="bg-transparent outline-none resize-none text-[15px] text-foreground min-h-[60px]"
        />
        <div className="flex gap-2 justify-end">
          <button onClick={() => setEditing(false)} className="text-xs px-3 py-1.5 rounded-lg hover:bg-primary text-muted-foreground">Cancel</button>
          <button
            onClick={() => { if (onEdit && editText.trim()) { onEdit(msg.id, editText.trim()); setEditing(false); } }}
            className="text-xs px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-gray-800"
          >Save & Submit</button>
        </div>
      </div>
    );
  }

  return (
    <div className="group relative bg-sidebar px-5 py-3 rounded-2xl rounded-tr-sm text-foreground text-[15px] leading-relaxed">
      {msg.attachments && msg.attachments.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-2">
          {msg.attachments.map((url, idx) => (
            <img key={idx} src={url} alt="attachment" className="h-32 w-auto object-cover rounded-xl border border-border shadow-sm" />
          ))}
        </div>
      )}
      {msg.text}
      {onEdit && (
        <button
          onClick={() => setEditing(true)}
          className="absolute -bottom-6 right-0 p-1 rounded-md text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
          title="Edit message"
        >
          <Pencil size={14} />
        </button>
      )}
    </div>
  );
}

// ---- Blinking cursor for streaming ----
function StreamingCursor() {
  return <span className="inline-block w-[2px] h-[1.1em] bg-primary animate-pulse ml-0.5 align-text-bottom" />;
}

// ---- Main component ----
interface ChatAreaProps {
  messages: Message[];
  isThinking: boolean;
  isStreaming: boolean;
  currentThought: string;
  onRegenerate?: () => void;
  onEditAndResend?: (id: string, text: string) => void;
  onRetry?: () => void;
  onSendSuggestion?: (text: string) => void;
}

export default function ChatArea({ messages, isThinking, isStreaming, currentThought, onRegenerate, onEditAndResend, onRetry }: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  // Smart scroll: detect if user has manually scrolled up
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setUserScrolledUp(!isAtBottom);
  }, []);

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (!userScrolledUp) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isThinking, currentThought, userScrolledUp]);

  // Always scroll to bottom when streaming finishes
  useEffect(() => {
    if (!isStreaming && !isThinking) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      const timer = setTimeout(() => setUserScrolledUp(false), 0);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, isThinking]);

  // Determine if the last message was an error (for retry button)
  const lastMsg = messages[messages.length - 1];
  const showRetry = lastMsg?.status === 'error';
  const showRegenerate = !isThinking && !isStreaming && lastMsg?.sender === 'aria' && lastMsg?.status === 'done';

  if (messages.length === 0 && !isThinking) {
    return <div className="flex-1 min-h-0" aria-hidden />;
  }

  return (
    <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-8 pb-32">
      <div className="max-w-3xl mx-auto flex flex-col gap-8">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 max-w-[85%] ${msg.sender === 'user' ? 'ml-auto flex-row-reverse' : ''}`}>
            {msg.sender === 'user' ? (
              <UserMessage msg={msg} onEdit={onEditAndResend} />
            ) : (
              <div className="py-1 text-foreground w-full overflow-hidden text-[15px] leading-relaxed">
                {/* Error state */}
                {msg.status === 'error' && (
                  <div className="flex items-center gap-2 text-red-500 text-sm mb-2 bg-red-50 px-3 py-2 rounded-lg border border-red-100">
                    <AlertTriangle size={14} />
                    <span>{msg.errorKind === 'network_error' ? 'Network error — connection lost.' : 'An error occurred generating a response.'}</span>
                  </div>
                )}
                {msg.text && (
                  <div className="prose prose-sm max-w-none prose-pre:bg-gray-50 prose-pre:border prose-pre:border-border prose-pre:text-foreground prose-p:leading-relaxed prose-headings:font-semibold">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeHighlight]}
                      components={{
                        pre: ({ children, ...props }) => <CodeBlock {...props}>{children}</CodeBlock>
                      }}
                    >
                      {msg.text}
                    </ReactMarkdown>
                    {msg.status === 'streaming' && <StreamingCursor />}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Thinking indicator (pre-streaming) */}
        {isThinking && (
          <div className="flex gap-4 max-w-[85%]">
            <div className="py-1 flex items-center gap-3">
              <div className="flex items-center gap-1.5 bg-sidebar px-4 py-3 rounded-2xl">
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '160ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '320ms' }} />
              </div>
              <span className="text-[13px] italic text-muted-foreground max-w-[300px] truncate">{currentThought}</span>
            </div>
          </div>
        )}

        {/* Action buttons at bottom of conversation */}
        {(showRegenerate || showRetry) && (
          <div className="flex gap-2 items-center">
            {showRegenerate && onRegenerate && (
              <button
                onClick={onRegenerate}
                className="flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground px-3 py-1.5 rounded-lg hover:bg-primary transition-colors"
              >
                <RefreshCw size={14} /> Regenerate
              </button>
            )}
            {showRetry && onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 text-[13px] text-red-500 hover:text-red-700 px-3 py-1.5 rounded-lg hover:bg-red-50 transition-colors"
              >
                <RotateCcw size={14} /> Retry
              </button>
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
