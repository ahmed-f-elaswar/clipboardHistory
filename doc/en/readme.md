# Clipboard History Manager

A Ditto-inspired clipboard history manager for NVDA.

Keeps track of everything you copy — text, files, links, and emails — with instant event-driven clipboard monitoring.

## Features

* **Instant clipboard monitoring** using Windows clipboard listener (event-driven, no polling).
* **File support**: Files copied in Explorer appear in history and paste back as actual files (CF_HDROP format).
* **Auto-grouping**: Entries are automatically categorized as Files and Folders, Links, or Emails.
* **Search and filter**: Full-text search and group filter in the history dialog.
* **Pin important entries** so they are never removed when the history limit is reached.
* **Multi-select and paste**: Select multiple entries with Ctrl+Space and paste in the order you selected them.
* **Append to clipboard**: Append selected text to the current clipboard content.
* **Reorder entries**: Move entries up/down with Shift+Arrow keys, or to top/bottom via context menu.
* **Save entries**: Save any entry as a Text (.txt) or Word (.docx) file from the context menu.
* **Pasted indicator**: Entries that have been pasted are marked with "Pasted:" in the list.
* **Combined paste**: When multiple entries are pasted together, the combined text is also saved as a new entry.
* **Persistent history**: History is saved between NVDA sessions (configurable).
* **Custom groups**: Create and manage custom groups for organizing entries.
* **Clip editor**: Create new clips from scratch or edit existing entries with a built-in text editor, complete with unsaved-changes warning.
* **Select all**: Press Ctrl+A in the history dialog to select all entries at once.
* **Configurable**: Settings panel in NVDA Preferences for max entries, persistence, and announcements.

## Global Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| NVDA+A | Open clipboard history dialog |
| NVDA+C | Announce current clipboard content |
| NVDA+Shift+A | Append selected text to latest clipboard entry |
| NVDA+Alt+Up Arrow | Navigate to previous history entry |
| NVDA+Alt+Down Arrow | Navigate to next history entry |
| NVDA+Alt+V | Paste the currently navigated entry |
| NVDA+Alt+Enter | Copy the currently navigated entry to clipboard |
| NVDA+Alt+Delete | Delete the currently navigated entry |
| NVDA+Alt+P | Pin/unpin the currently navigated entry |
| NVDA+Alt+X | Clear all clipboard history |
| NVDA+Shift+C | Open editor to write a new clip |
| NVDA+Alt+G | Set group for the currently navigated entry |

## Dialog Keyboard Shortcuts

When the Clipboard History dialog is open:

| Shortcut | Action |
|---|---|
| Enter | Paste selected entry/entries |
| Ctrl+Space | Toggle multi-select (selection-order aware) |
| Delete | Delete selected entry/entries |
| Ctrl+A | Select all entries |
| Ctrl+E | Edit selected entry |
| Ctrl+P | Pin/unpin entry |
| Ctrl+G | Set group |
| Shift+Up Arrow | Move entry up in the list |
| Shift+Down Arrow | Move entry down in the list |
| Applications key | Open context menu |
| Alt+S | Focus search field |
| Alt+U | Focus group filter |
| Alt+G | Set group button |
| Escape | Close dialog |

## Context Menu Options

Right-click or press the Applications key on any entry:

* Paste
* Copy to Clipboard
* Edit
* **Save As** submenu: Text File (.txt), Word Document (.docx)
* **Move To** submenu: Top, Bottom
* Pin / Unpin
* Set Group
* Delete

## Settings

Available in NVDA menu > Preferences > Settings > Clipboard History:

* **Maximum number of history entries**: Set the limit (10–10,000, default 500). When exceeded, the oldest unpinned entry is removed.
* **Save history between NVDA sessions**: Keep history persistent across restarts (default: on).
* **Announce when new text is copied**: Speak a preview when new content is detected (default: off).

## Compatibility

* Minimum NVDA version: 2024.1
* Last tested: NVDA 2025.3

## License

GNU General Public License, version 2.
