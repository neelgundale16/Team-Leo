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
  if (
    file.type.includes('word') ||
    file.name.endsWith('.doc') ||
    file.name.endsWith('.docx')
  )
    return 'doc';
  return 'other';
}

function FileChip({
  attachment,
  onRemove,
}: {
  attachment: AttachedFile;
  onRemove: () => void;
}) {
  const icons: Record<AttachedFile['type'], string> = {
    pdf:   '📄',
    image: '🖼️',
    doc:   '📝',
    other: '📎',
  };

  return (
    <div className="file-chip">
      {attachment.type === 'image' && attachment.previewUrl ? (
        <img
          src={attachment.previewUrl}
          alt={attachment.file.name}
          className="chip-img-preview"
        />
      ) : (
        <span className="chip-icon">{icons[attachment.type]}</span>
      )}
      <span className="chip-name">
        {attachment.file.name.length > 18
          ? attachment.file.name.slice(0, 15) + '…'
          : attachment.file.name}
      </span>
      <button
        className="chip-remove"
        onClick={onRemove}
        title="Remove"
        type="button"
      >
        ×
      </button>
    </div>
  );
}

export default function QueryInput({ onSubmit, isLoading }: QueryInputProps) {
  const [value, setValue]             = useState('');
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);

  const fileInputRef  = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if ((!trimmed && attachments.length === 0) || isLoading) return;
    onSubmit(trimmed, attachments);
    setValue('');
    setAttachments([]);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const newAttachments: AttachedFile[] = Array.from(files).map((file) => {
      const type = getFileType(file);
      const previewUrl =
        type === 'image' ? URL.createObjectURL(file) : undefined;
      return { file, type, previewUrl };
    });
    setAttachments((prev) => [...prev, ...newAttachments]);
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => {
      const updated = [...prev];
      if (updated[index].previewUrl) {
        URL.revokeObjectURL(updated[index].previewUrl!);
      }
      updated.splice(index, 1);
      return updated;
    });
  };

  return (
    <div className="query-input-wrapper">
      {/* Attached file chips */}
      {attachments.length > 0 && (
        <div className="file-chips-row">
          {attachments.map((att, i) => (
            <FileChip
              key={i}
              attachment={att}
              onRemove={() => removeAttachment(i)}
            />
          ))}
        </div>
      )}

      <div className="input-row">
        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt,.csv,.json"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}
        />
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}
        />

        {/* Upload buttons */}
        <div className="upload-btns">
          <button
            type="button"
            className="upload-btn"
            title="Attach PDF / DOC / TXT"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
          >
            {/* File icon */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="12" y1="18" x2="12" y2="12"/>
              <line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
            <span className="upload-btn-label">File</span>
          </button>

          <button
            type="button"
            className="upload-btn"
            title="Attach Image"
            onClick={() => imageInputRef.current?.click()}
            disabled={isLoading}
          >
            {/* Image icon */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
            <span className="upload-btn-label">Image</span>
          </button>
        </div>

        {/* Text input */}
        <div className="input-container">
          <span className="prompt-symbol">›</span>
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about financial data, company metrics..."
            disabled={isLoading}
            className="query-input"
            autoFocus
          />
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={isLoading || (!value.trim() && attachments.length === 0)}
          className="submit-btn"
        >
          {isLoading ? (
            <span className="spinner-wrap">
              <span className="spinner" />
              <span>SCANNING</span>
            </span>
          ) : (
            <span>FIRE</span>
          )}
        </button>
      </div>

      <div className="input-underline" />
    </div>
  );
}