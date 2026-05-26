// Verbatim port of JARVIS/app/icons.jsx — same SVGs, same keys.
import type { ReactNode } from "react";

export const I: Record<string, ReactNode> = {
  send: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M2 8 L14 2 L8 14 L7 9 L2 8z" />
    </svg>
  ),
  cmd: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="2" y="2" width="4" height="4" rx="1.5" />
      <rect x="10" y="2" width="4" height="4" rx="1.5" />
      <rect x="2" y="10" width="4" height="4" rx="1.5" />
      <rect x="10" y="10" width="4" height="4" rx="1.5" />
      <line x1="6" y1="4" x2="10" y2="4" />
      <line x1="4" y1="6" x2="4" y2="10" />
      <line x1="6" y1="12" x2="10" y2="12" />
      <line x1="12" y1="6" x2="12" y2="10" />
    </svg>
  ),
  trash: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3 4h10M6 4V2.5h4V4M5 4l1 9h4l1-9" />
    </svg>
  ),
  refresh: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3 8a5 5 0 1 1 1.5 3.5" />
      <polyline points="3 11.5 3 8 6.5 8" />
    </svg>
  ),
  caret: (
    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3 5l3 3 3-3" />
    </svg>
  ),
  chevron: (
    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M4.5 3l3 3-3 3" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="7" cy="7" r="4.5" />
      <line x1="10.5" y1="10.5" x2="14" y2="14" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 8.5 L7 12 L13 4" />
    </svg>
  ),
  x: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 4 L12 12 M12 4 L4 12" />
    </svg>
  ),
  thumbsUp: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M5 13V7l3-4 1 .5V7h3.5l1 1.5L13 13z" />
      <line x1="3" y1="7" x2="3" y2="13" />
    </svg>
  ),
  cam: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <rect x="2" y="4" width="9" height="8" rx="1.5" />
      <path d="M11 7l3-1.5v5L11 9" />
    </svg>
  ),
  more: (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <circle cx="3" cy="8" r="1.2" />
      <circle cx="8" cy="8" r="1.2" />
      <circle cx="13" cy="8" r="1.2" />
    </svg>
  ),
};
