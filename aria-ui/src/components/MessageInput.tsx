import { useState, useRef, ClipboardEvent } from 'react';
import { Add01Icon as Plus, ArrowUp01Icon as Send, Cancel01Icon as X, Square01Icon as Square } from 'hugeicons-react';

interface Attachment {
  file: File;
  previewUrl: string;
}

interface Props {
  onSend: (msg: string, files?: File[]) => void;
  onStop: () => void;
  isDisabled: boolean; // true when streaming/thinking
}

export default function MessageInput({ onSend, onStop, isDisabled }: Props) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (file) addAttachment(file);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      Array.from(e.target.files).forEach(file => {
        if (file.type.startsWith('image/')) addAttachment(file);
      });
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const addAttachment = (file: File) => {
    const previewUrl = URL.createObjectURL(file);
    setAttachments(prev => [...prev, { file, previewUrl }]);
  };

  const removeAttachment = (index: number) => {
    setAttachments(prev => {
      const newAtt = [...prev];
      URL.revokeObjectURL(newAtt[index].previewUrl);
      newAtt.splice(index, 1);
      return newAtt;
    });
  };

  const submitMessage = () => {
    if (isDisabled) return;
    if (text.trim() || attachments.length > 0) {
      onSend(text.trim(), attachments.map(a => a.file));
      setText('');
      setAttachments([]);
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitMessage();
    }
  };

  const hasContent = text.trim() || attachments.length > 0;

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-2 bg-[#212121] backdrop-blur-2xl border border-border shadow-[0_8px_30px_rgb(0,0,0,0.06)] rounded-full p-2 pr-3 transition-all focus-within:shadow-[0_12px_40px_rgb(0,0,0,0.12)] focus-within:-translate-y-0.5">

      {/* Attachments Preview */}
      {attachments.length > 0 && (
        <div className="flex gap-2 flex-wrap px-3 pt-2">
          {attachments.map((att, idx) => (
            <div key={idx} className="relative group">
              <img src={att.previewUrl} alt="attachment" className="h-16 w-16 object-cover rounded-xl border border-border shadow-sm" />
              <button
                onClick={() => removeAttachment(idx)}
                className="absolute -top-2 -right-2 bg-primary text-primary-foreground rounded-full p-1 shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end gap-3 w-full">
        <input
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileSelect}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="p-2 mb-1 rounded-full text-muted-foreground hover:text-foreground hover:bg-primary transition-colors shrink-0"
          title="Attach image"
          disabled={isDisabled}
        >
          <Plus size={22} />
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => { setText(e.target.value); handleInput(); }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={isDisabled ? "ARIA is responding..." : "Message ARIA..."}
          disabled={isDisabled}
          className="flex-1 max-h-48 min-h-[24px] py-3 bg-transparent resize-none outline-none text-[15px] leading-relaxed text-foreground placeholder:text-muted-foreground font-sans disabled:opacity-50 disabled:cursor-not-allowed"
          rows={1}
        />

        {/* Send or Stop button */}
        {isDisabled ? (
          <button
            onClick={onStop}
            className="p-2 mb-1 rounded-full bg-primary text-primary-foreground hover:bg-accent transition-all shrink-0"
            title="Stop generating"
          >
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={submitMessage}
            className={`p-2 mb-1 rounded-full transition-all shrink-0 ${hasContent ? 'bg-primary text-primary-foreground hover:bg-accent scale-100' : 'bg-secondary text-muted-foreground scale-95'}`}
            disabled={!hasContent}
          >
            <Send size={16} className="ml-0.5" />
          </button>
        )}
      </div>
    </div>
  );
}
