'use client';

import { useState, KeyboardEvent, useRef } from 'react';

export interface AttachedFile {
  file: File;
  type: 'pdf' | 'image' | 'doc' | 'other';
  previewUrl?: string;
}

interface QueryInputProps {
  onSubmit: (query: string, attachments: AttachedFile[]) => void;
  isLoading: boolean;
}

function getFileType(file: File): AttachedFile['type'] {
  if (file.type === 'application/pdf') return 'pdf';
  if (file.type.startsWith('image/')) return 'image';
  if (file.type.includes('word') || file.name.endsWith('.doc') || file.name.endsWith('.docx')) return 'doc';
  return 'other';
}

const chipIcons: Record<AttachedFile['type'], string> = {
  pdf: '📄', image: '🖼️', doc: '📝', other: '📎',
};

function FileChip({ attachment, onRemove }: { attachment: AttachedFile; onRemove: () => void }) {
  return (
    <div className="file-chip">
      {attachment.type === 'image' && attachment.previewUrl ? (
        <img src={attachment.previewUrl} alt="" className="chip-img-preview" />
      ) : (
        <span style={{ fontSize: '0.8rem' }}>{chipIcons[attachment.type]}</span>
      )}
      <span className="chip-name">
        {attachment.file.name.length > 20 ? attachment.file.name.slice(0, 17) + '…' : attachment.file.name}
      </span>
      <button className="chip-remove" onClick={onRemove} type="button" title="Remove">×</button>
    </div>
  );
}

export default function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [value, setValue]             = useState('');
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const canSubmit = (value.trim().length > 0 || attachments.length > 0) && !isLoading;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit(value.trim(), attachments);
    setValue('');
    setAttachments([]);
  };

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) handleSubmit();
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const next: AttachedFile[] = Array.from(files).map((f) => {
      const type = getFileType(f);
      return { file: f, type, previewUrl: type === 'image' ? URL.createObjectURL(f) : undefined };
    });
    setAttachments((p) => [...p, ...next]);
  };

  const remove = (i: number) => {
    setAttachments((p) => {
      const n = [...p];
      if (n[i].previewUrl) URL.revokeObjectURL(n[i].previewUrl!);
      n.splice(i, 1);
      return n;
    });
  };

  return (
    <div className="query-card">
      {/* Hidden inputs */}
      <input ref={fileRef}  type="file" accept=".pdf,.doc,.docx,.txt,.csv,.json" multiple style={{ display: 'none' }}
        onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />

      {/* Attached chips */}
      {attachments.length > 0 && (
        <div className="query-chips-area">
          {attachments.map((a, i) => (
            <FileChip key={i} attachment={a} onRemove={() => remove(i)} />
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="query-input-row">
        <span className="query-prompt">›</span>

        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about financial data, company metrics, legal documents…"
          disabled={isLoading}
          className="query-input"
          autoFocus
        />

        <div className="query-actions">
          {/* File attach */}
          <button
            type="button"
            className="icon-btn"
            title="Attach document (PDF, DOC, TXT, CSV)"
            onClick={() => fileRef.current?.click()}
            disabled={isLoading}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="18" x2="12" y2="12"/>
              <line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
          </button>

          <div className="icon-btn-divider" />

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`submit-btn ${isLoading ? 'loading' : ''}`}
          >
            {isLoading ? (
              <>
                <span className="spinner" />
                Scanning…
              </>
            ) : (
              <>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
                Analyse
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}