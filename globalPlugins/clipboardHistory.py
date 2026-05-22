# NVDA Global Plugin: Clipboard History Manager
# Inspired by Ditto Clipboard Manager for Windows
# Licensed under the GNU General Public License (version 2).
# https://github.com/nvdaes/clipboardHistory

import json
import os
import time
import threading
import ctypes
import ctypes.wintypes
import zipfile

import wx

import api
import addonHandler
import config
import globalPluginHandler
import globalVars
import gui
import tones
import ui
import windowUtils
from scriptHandler import script, getLastScriptRepeatCount
from logHandler import log
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel

addonHandler.initTranslation()

CONFIG_SECTION = "clipboardHistory"
# Store history in NVDA's user config directory
_DATA_DIR = os.path.join(globalVars.appArgs.configPath, "clipboardHistory")
os.makedirs(_DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(_DATA_DIR, "clipboard_history.json")
GROUPS_FILE = os.path.join(_DATA_DIR, "clipboard_groups.json")

DEFAULT_MAX_ENTRIES = 500
MIN_MAX_ENTRIES = 10
MAX_MAX_ENTRIES = 10000

DEFAULT_POLL_INTERVAL = 500  # ms - fallback only

# Windows message for clipboard changes
WM_CLIPBOARDUPDATE = 0x031D

# Limit stored text size to prevent memory issues (64 KB per entry)
MAX_ENTRY_LENGTH = 65536

FILES_AND_FOLDERS_GROUP = "Files and Folders"
LINKS_GROUP = "Links"
EMAILS_GROUP = "Emails"

# Display names for auto-detected groups (translatable)
_GROUP_DISPLAY = {
	FILES_AND_FOLDERS_GROUP: _("Files and Folders"),
	LINKS_GROUP: _("Links"),
	EMAILS_GROUP: _("Emails"),
}


def _group_display_name(group):
	"""Return the translated display name for a group, or the group name itself."""
	return _GROUP_DISPLAY.get(group, group)


# Patterns to detect file/folder paths
import re
_PATH_PATTERN = re.compile(
	r'^(?:[A-Za-z]:\\|\\\\|/)[^\x00-\x1f]*$',
	re.MULTILINE,
)
_URL_PATTERN = re.compile(
	r'https?://[^\s<>"]+|www\.[^\s<>"]+',
	re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(
	r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
)

# Windows clipboard format for file drops
CF_HDROP = 15


def _get_clipboard_file_paths():
	"""Read file paths from the clipboard if files/folders were copied (CF_HDROP).
	Returns a list of file path strings, or an empty list.
	"""
	shell32 = ctypes.windll.shell32
	user32 = ctypes.windll.user32

	if not user32.OpenClipboard(0):
		log.debug("Clipboard History: _get_clipboard_file_paths: OpenClipboard failed")
		return []
	try:
		h_drop = user32.GetClipboardData(CF_HDROP)
		if not h_drop:
			log.debug("Clipboard History: _get_clipboard_file_paths: No CF_HDROP data")
			return []
		# DragQueryFileW with index 0xFFFFFFFF returns the count of files
		count = shell32.DragQueryFileW(h_drop, 0xFFFFFFFF, None, 0)
		paths = []
		buf = ctypes.create_unicode_buffer(1024)
		for i in range(count):
			length = shell32.DragQueryFileW(h_drop, i, buf, 1024)
			if length:
				paths.append(buf.value)
		log.debug(f"Clipboard History: _get_clipboard_file_paths: found {len(paths)} paths")
		return paths
	except Exception:
		log.error("Clipboard History: _get_clipboard_file_paths error", exc_info=True)
		return []
	finally:
		user32.CloseClipboard()


def _copy_files_to_clipboard(file_paths):
	"""Copy file paths to clipboard in CF_HDROP format so Explorer can paste them.
	Uses pure ctypes Win32 API calls for maximum compatibility.
	"""
	import struct

	if not file_paths:
		return False

	# Filter out empty lines
	file_paths = [p.strip() for p in file_paths if p.strip()]
	if not file_paths:
		return False

	log.debug(f"Clipboard History: _copy_files_to_clipboard called with paths: {file_paths}")

	kernel32 = ctypes.windll.kernel32
	user32 = ctypes.windll.user32

	# Set proper function signatures for pointer-safe calls
	kernel32.GlobalAlloc.restype = ctypes.c_void_p
	kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
	kernel32.GlobalLock.restype = ctypes.c_void_p
	kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalUnlock.restype = ctypes.c_int
	kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
	kernel32.GlobalFree.restype = ctypes.c_void_p
	kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
	user32.SetClipboardData.restype = ctypes.c_void_p
	user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

	GMEM_MOVEABLE = 0x0002

	try:
		# Build DROPFILES struct + file path data
		header = struct.pack('<I II I I', 20, 0, 0, 0, 1)
		file_data = b""
		for path in file_paths:
			file_data += path.encode("utf-16-le") + b"\x00\x00"
		file_data += b"\x00\x00"
		payload = header + file_data
		total_size = len(payload)

		# Allocate global memory for DROPFILES
		h_drop = kernel32.GlobalAlloc(GMEM_MOVEABLE, total_size)
		if not h_drop:
			log.error("Clipboard History: GlobalAlloc failed for DROPFILES")
			return False
		p_drop = kernel32.GlobalLock(h_drop)
		if not p_drop:
			kernel32.GlobalFree(h_drop)
			log.error("Clipboard History: GlobalLock failed for DROPFILES")
			return False
		ctypes.memmove(p_drop, payload, total_size)
		kernel32.GlobalUnlock(h_drop)

		# Allocate Preferred DropEffect
		cf_dropeffect = user32.RegisterClipboardFormatW("Preferred DropEffect")
		effect_data = struct.pack('<I', 5)  # DROPEFFECT_COPY | DROPEFFECT_LINK
		h_effect = kernel32.GlobalAlloc(GMEM_MOVEABLE, 4)
		if h_effect:
			p_effect = kernel32.GlobalLock(h_effect)
			if p_effect:
				ctypes.memmove(p_effect, effect_data, 4)
				kernel32.GlobalUnlock(h_effect)

		# Set clipboard
		if not user32.OpenClipboard(0):
			kernel32.GlobalFree(h_drop)
			if h_effect:
				kernel32.GlobalFree(h_effect)
			log.error("Clipboard History: OpenClipboard failed")
			return False

		user32.EmptyClipboard()
		result = user32.SetClipboardData(CF_HDROP, h_drop)
		if not result:
			log.error(f"Clipboard History: SetClipboardData CF_HDROP failed, error={ctypes.GetLastError()}")
			user32.CloseClipboard()
			return False

		if cf_dropeffect and h_effect:
			user32.SetClipboardData(cf_dropeffect, h_effect)

		user32.CloseClipboard()

		log.debug(f"Clipboard History: Set CF_HDROP with {len(file_paths)} file(s) successfully")
		return True
	except Exception:
		log.error("Clipboard History: Failed to copy files to clipboard", exc_info=True)
		return False


def _is_file_path_text(text):
	"""Check if text looks like file/folder paths."""
	for line in text.strip().splitlines():
		line = line.strip()
		if not line:
			continue
		if _PATH_PATTERN.match(line):
			return True
	return False


class ClipboardEntry:
	"""Represents a single clipboard history entry."""

	def __init__(self, text, timestamp=None, pinned=False, entry_id=None, group="", pasted=False):
		self.text = text
		self.timestamp = timestamp or time.time()
		self.pinned = pinned
		self.entry_id = entry_id or int(self.timestamp * 1000)
		self.group = group
		self.pasted = pasted

	def to_dict(self):
		d = {
			"text": self.text,
			"timestamp": self.timestamp,
			"pinned": self.pinned,
			"entry_id": self.entry_id,
			"group": self.group,
		}
		if self.pasted:
			d["pasted"] = True
		return d

	@classmethod
	def from_dict(cls, data):
		return cls(
			text=data["text"],
			timestamp=data.get("timestamp", time.time()),
			pinned=data.get("pinned", False),
			entry_id=data.get("entry_id"),
			group=data.get("group", ""),
			pasted=data.get("pasted", False),
		)

	def get_preview(self, max_length=80):
		"""Get a short preview of the text for display."""
		if self.group == FILES_AND_FOLDERS_GROUP:
			lines = self.text.strip().splitlines()
			names = [os.path.basename(l.strip()) for l in lines if l.strip()]
			if len(names) == 1:
				text = f"{names[0]} - {lines[0].strip()}"
			else:
				text = _("%d files: %s") % (len(names), ', '.join(names))
		else:
			text = self.text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
		if len(text) > max_length:
			text = text[:max_length] + "..."
		return text


class ClipboardHistoryManager:
	"""Manages the clipboard history storage and retrieval."""

	def __init__(self, max_entries=DEFAULT_MAX_ENTRIES):
		self.max_entries = max_entries
		self._entries = []
		self._groups = set()
		self._lock = threading.Lock()
		self._load_groups()
		self._load_history()

	def add(self, text):
		"""Add a new clipboard entry. Returns True if added, False if duplicate of most recent."""
		if not text or not text.strip():
			return False
		# Truncate overly long entries
		if len(text) > MAX_ENTRY_LENGTH:
			text = text[:MAX_ENTRY_LENGTH]
		with self._lock:
			# Check if it's identical to the most recent non-pinned entry
			if self._entries:
				for entry in self._entries:
					if not entry.pinned:
						if entry.text == text:
							# Move it to the top instead of adding a duplicate
							self._entries.remove(entry)
							entry.timestamp = time.time()
							self._entries.insert(0, entry)
							self._save_history()
							return True
						break

			entry = ClipboardEntry(text, group=self._detect_group(text))
			self._entries.insert(0, entry)
			self._trim()
			self._save_history()
			return True

	def mark_pasted(self, entry_ids):
		"""Mark the given entries as pasted and move them to the top."""
		with self._lock:
			# Move pasted entries to top (in order) and mark them
			to_move = []
			remaining = []
			for entry in self._entries:
				if entry.entry_id in entry_ids:
					entry.pasted = True
					entry.timestamp = time.time()
					to_move.append(entry)
				else:
					remaining.append(entry)
			self._entries = to_move + remaining
			self._save_history()

	def get_all(self):
		"""Get all entries."""
		with self._lock:
			return list(self._entries)

	def swap_entries(self, idx_a, idx_b):
		"""Swap two entries by index. Returns True if swapped."""
		with self._lock:
			if 0 <= idx_a < len(self._entries) and 0 <= idx_b < len(self._entries):
				self._entries[idx_a], self._entries[idx_b] = self._entries[idx_b], self._entries[idx_a]
				self._save_history()
				return True
			return False

	def move_to_position(self, entry_id, position):
		"""Move an entry to a specific position ('top' or 'bottom'). Returns True if moved."""
		with self._lock:
			entry = None
			for i, e in enumerate(self._entries):
				if e.entry_id == entry_id:
					entry = self._entries.pop(i)
					break
			if not entry:
				return False
			if position == "top":
				self._entries.insert(0, entry)
			else:
				self._entries.append(entry)
			self._save_history()
			return True

	def get_entry(self, index):
		"""Get entry at the given index."""
		with self._lock:
			if 0 <= index < len(self._entries):
				return self._entries[index]
		return None

	def search(self, query):
		"""Search entries by text content. Case-insensitive."""
		query_lower = query.lower()
		with self._lock:
			return [e for e in self._entries if query_lower in e.text.lower()]

	def delete(self, entry_id):
		"""Delete an entry by its ID."""
		with self._lock:
			self._entries = [e for e in self._entries if e.entry_id != entry_id]
			self._save_history()

	def toggle_pin(self, entry_id):
		"""Toggle the pinned state of an entry."""
		with self._lock:
			for entry in self._entries:
				if entry.entry_id == entry_id:
					entry.pinned = not entry.pinned
					self._save_history()
					return entry.pinned
		return False

	def clear_unpinned(self):
		"""Clear all unpinned entries."""
		with self._lock:
			self._entries = [e for e in self._entries if e.pinned]
			self._save_history()

	def clear_all(self):
		"""Clear all entries including pinned."""
		with self._lock:
			self._entries.clear()
			self._save_history()

	def set_group(self, entry_id, group_name):
		"""Set the group for an entry."""
		with self._lock:
			for entry in self._entries:
				if entry.entry_id == entry_id:
					entry.group = group_name
					self._save_history()
					return True
		return False

	def update_text(self, entry_id, new_text):
		"""Update the text of an entry. Returns True if updated."""
		if not new_text or not new_text.strip():
			return False
		if len(new_text) > MAX_ENTRY_LENGTH:
			new_text = new_text[:MAX_ENTRY_LENGTH]
		with self._lock:
			for entry in self._entries:
				if entry.entry_id == entry_id:
					entry.text = new_text
					entry.group = self._detect_group(new_text)
					self._save_history()
					return True
		return False

	def get_groups(self):
		"""Get a sorted list of all group names (registered + in-use)."""
		with self._lock:
			groups = set(self._groups)
			for entry in self._entries:
				if entry.group:
					groups.add(entry.group)
			return sorted(groups)

	def create_group(self, name):
		"""Create a new named group. Returns True if created, False if it already exists."""
		name = name.strip()
		if not name:
			return False
		with self._lock:
			if name in self._groups:
				return False
			self._groups.add(name)
			self._save_groups()
			return True

	def delete_group(self, name):
		"""Delete a group and unassign all its entries."""
		with self._lock:
			self._groups.discard(name)
			for entry in self._entries:
				if entry.group == name:
					entry.group = ""
			self._save_groups()
			self._save_history()

	def rename_group(self, old_name, new_name):
		"""Rename a group and update all entries."""
		new_name = new_name.strip()
		if not new_name:
			return False
		with self._lock:
			self._groups.discard(old_name)
			self._groups.add(new_name)
			for entry in self._entries:
				if entry.group == old_name:
					entry.group = new_name
			self._save_groups()
			self._save_history()
			return True

	def get_by_group(self, group_name):
		"""Get all entries in a specific group."""
		with self._lock:
			return [e for e in self._entries if e.group == group_name]

	@staticmethod
	def _detect_group(text):
		"""Auto-detect group based on text content: file paths, links, or emails."""
		for line in text.strip().splitlines():
			line = line.strip()
			if not line:
				continue
			if _PATH_PATTERN.match(line):
				return FILES_AND_FOLDERS_GROUP
		if _EMAIL_PATTERN.search(text):
			return EMAILS_GROUP
		if _URL_PATTERN.search(text):
			return LINKS_GROUP
		return ""

	@property
	def count(self):
		with self._lock:
			return len(self._entries)

	def _trim(self):
		"""Remove oldest unpinned entries to stay within max_entries limit."""
		while len(self._entries) > self.max_entries:
			for i in range(len(self._entries) - 1, -1, -1):
				if not self._entries[i].pinned:
					del self._entries[i]
					break
			else:
				break

	def _save_history(self):
		"""Save history to disk."""
		try:
			data = [e.to_dict() for e in self._entries]
			with open(HISTORY_FILE, "w", encoding="utf-8") as f:
				json.dump(data, f, ensure_ascii=False, indent=None)
		except Exception:
			log.error("Clipboard History: Failed to save history", exc_info=True)

	def _save_groups(self):
		"""Save registered group names to disk."""
		try:
			with open(GROUPS_FILE, "w", encoding="utf-8") as f:
				json.dump(sorted(self._groups), f, ensure_ascii=False)
		except Exception:
			log.error("Clipboard History: Failed to save groups", exc_info=True)

	def _load_groups(self):
		"""Load registered group names from disk."""
		if not os.path.exists(GROUPS_FILE):
			return
		try:
			with open(GROUPS_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
			if isinstance(data, list):
				self._groups = set(str(g) for g in data if g)
		except Exception:
			log.error("Clipboard History: Failed to load groups", exc_info=True)

	def _load_history(self):
		"""Load history from disk."""
		if not os.path.exists(HISTORY_FILE):
			return
		try:
			with open(HISTORY_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
			if not isinstance(data, list):
				return
			for item in data:
				if isinstance(item, dict) and "text" in item:
					self._entries.append(ClipboardEntry.from_dict(item))
			self._trim()
		except Exception:
			log.error("Clipboard History: Failed to load history", exc_info=True)


class GroupDialog(wx.Dialog):
	"""Dialog to assign a clip to a group - pick existing or create new."""

	def __init__(self, parent, existing_groups, current_group=""):
		super().__init__(parent, title=_("Set Group"), style=wx.DEFAULT_DIALOG_STYLE)
		self._group_name = current_group
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel = wx.Panel(self)
		pSizer = wx.BoxSizer(wx.VERTICAL)

		# Existing groups list
		if existing_groups:
			groupLabel = wx.StaticText(panel, label=_("Select an &existing group:"))
			pSizer.Add(groupLabel, 0, wx.ALL, 5)
			self._groupList = wx.ListBox(panel, choices=existing_groups)
			if current_group in existing_groups:
				self._groupList.SetStringSelection(current_group)
			self._groupList.Bind(wx.EVT_LISTBOX, self._on_group_selected)
			self._groupList.Bind(wx.EVT_LISTBOX_DCLICK, self._on_ok)
			pSizer.Add(self._groupList, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
		else:
			self._groupList = None

		# New group name
		newLabel = wx.StaticText(panel, label=_("Or type a &new group name:"))
		pSizer.Add(newLabel, 0, wx.ALL, 5)
		self._newGroupCtrl = wx.TextCtrl(panel)
		self._newGroupCtrl.SetValue(current_group)
		self._newGroupCtrl.Bind(wx.EVT_TEXT, self._on_text_changed)
		pSizer.Add(self._newGroupCtrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

		# Remove from group button
		self._removeBtn = wx.Button(panel, label=_("&Remove from group"))
		self._removeBtn.Bind(wx.EVT_BUTTON, self._on_remove)
		pSizer.Add(self._removeBtn, 0, wx.ALL, 5)

		# OK / Cancel
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		okBtn = wx.Button(panel, wx.ID_OK, label=_("OK"))
		okBtn.Bind(wx.EVT_BUTTON, self._on_ok)
		okBtn.SetDefault()
		btnSizer.Add(okBtn, 0, wx.RIGHT, 5)
		cancelBtn = wx.Button(panel, wx.ID_CANCEL, label=_("Cancel"))
		btnSizer.Add(cancelBtn, 0)
		pSizer.Add(btnSizer, 0, wx.EXPAND | wx.ALL, 5)

		panel.SetSizer(pSizer)
		sizer.Add(panel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetSize((350, 320))
		self.CentreOnParent()

	def _on_group_selected(self, event):
		sel = self._groupList.GetStringSelection()
		if sel:
			self._newGroupCtrl.SetValue(sel)

	def _on_text_changed(self, event):
		# Deselect the list if user is typing a custom name
		if self._groupList:
			typed = self._newGroupCtrl.GetValue()
			if typed not in [self._groupList.GetString(i) for i in range(self._groupList.GetCount())]:
				self._groupList.SetSelection(wx.NOT_FOUND)

	def _on_remove(self, event):
		self._group_name = ""
		self.EndModal(wx.ID_OK)

	def _on_ok(self, event):
		self._group_name = self._newGroupCtrl.GetValue().strip()
		self.EndModal(wx.ID_OK)

	def get_group_name(self):
		return self._group_name


class ManageGroupsDialog(wx.Dialog):
	"""Dialog to view, rename, and delete groups."""

	def __init__(self, parent, history_manager):
		super().__init__(parent, title=_("Manage Groups"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._history = history_manager
		self._build_ui()
		self._refresh_list()
		self.SetSize((400, 350))
		self.CentreOnParent()

	def _build_ui(self):
		sizer = wx.BoxSizer(wx.VERTICAL)
		panel = wx.Panel(self)
		pSizer = wx.BoxSizer(wx.VERTICAL)

		label = wx.StaticText(panel, label=_("&Groups:"))
		pSizer.Add(label, 0, wx.ALL, 5)

		self._listBox = wx.ListBox(panel)
		pSizer.Add(self._listBox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)

		self._newBtn = wx.Button(panel, label=_("&New"))
		self._newBtn.Bind(wx.EVT_BUTTON, self._on_new)
		btnSizer.Add(self._newBtn, 0, wx.RIGHT, 5)

		self._renameBtn = wx.Button(panel, label=_("&Rename"))
		self._renameBtn.Bind(wx.EVT_BUTTON, self._on_rename)
		btnSizer.Add(self._renameBtn, 0, wx.RIGHT, 5)

		self._deleteBtn = wx.Button(panel, label=_("&Delete"))
		self._deleteBtn.Bind(wx.EVT_BUTTON, self._on_delete)
		btnSizer.Add(self._deleteBtn, 0, wx.RIGHT, 5)

		closeBtn = wx.Button(panel, wx.ID_CLOSE, label=_("&Close"))
		closeBtn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
		btnSizer.Add(closeBtn, 0)

		pSizer.Add(btnSizer, 0, wx.ALL, 5)

		panel.SetSizer(pSizer)
		sizer.Add(panel, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetEscapeId(wx.ID_CLOSE)

	def _refresh_list(self):
		self._listBox.Set(self._history.get_groups())

	def _on_new(self, event):
		dlg = wx.TextEntryDialog(self, _("Enter a name for the new group:"), _("New Group"))
		if dlg.ShowModal() == wx.ID_OK:
			name = dlg.GetValue().strip()
			if not name:
				ui.message(_("Group name cannot be empty"))
			elif self._history.create_group(name):
				ui.message(_("Group created: %s") % name)
				self._refresh_list()
			else:
				ui.message(_("Group '%s' already exists") % name)
		dlg.Destroy()

	def _on_rename(self, event):
		sel = self._listBox.GetSelection()
		if sel == wx.NOT_FOUND:
			ui.message(_("Select a group first"))
			return
		old_name = self._listBox.GetString(sel)
		dlg = wx.TextEntryDialog(self, _("New name for '%s':") % old_name, _("Rename Group"), old_name)
		if dlg.ShowModal() == wx.ID_OK:
			new_name = dlg.GetValue().strip()
			if new_name and new_name != old_name:
				self._history.rename_group(old_name, new_name)
				ui.message(_("Renamed to: %s") % new_name)
				self._refresh_list()
		dlg.Destroy()

	def _on_delete(self, event):
		sel = self._listBox.GetSelection()
		if sel == wx.NOT_FOUND:
			ui.message(_("Select a group first"))
			return
		name = self._listBox.GetString(sel)
		if gui.messageBox(
			_("Delete group '%s'? Clips in this group will be unassigned but not deleted.") % name,
			_("Delete Group"),
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
			self,
		) == wx.YES:
			self._history.delete_group(name)
			ui.message(_("Group '%s' deleted") % name)
			self._refresh_list()


class ClipEditorDialog(wx.Dialog):
	"""Editor dialog for clip text with save, discard, and unsaved-changes warning."""

	def __init__(self, parent, text, title=None):
		super().__init__(parent, title=title or _("Edit Clip"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self._original_text = text
		self._dirty = False

		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		label = wx.StaticText(panel, label=_("Edit the clip &text:"))
		sizer.Add(label, 0, wx.ALL, 5)

		self._textCtrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_DONTWRAP | wx.TE_RICH2)
		self._textCtrl.SetValue(text)
		self._textCtrl.Bind(wx.EVT_TEXT, self._on_text_changed)
		sizer.Add(self._textCtrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		saveBtn = wx.Button(panel, wx.ID_OK, label=_("&Save"))
		saveBtn.SetDefault()
		btnSizer.Add(saveBtn, 0, wx.RIGHT, 5)
		discardBtn = wx.Button(panel, wx.ID_CANCEL, label=_("&Discard"))
		btnSizer.Add(discardBtn, 0)
		sizer.Add(btnSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

		panel.SetSizer(sizer)
		dlgSizer = wx.BoxSizer(wx.VERTICAL)
		dlgSizer.Add(panel, 1, wx.EXPAND)
		self.SetSizer(dlgSizer)
		self.SetSize((600, 400))
		self.CentreOnParent()

		self.Bind(wx.EVT_CLOSE, self._on_close)
		self.SetEscapeId(wx.ID_NONE)
		self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

	def _on_key(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		else:
			event.Skip()

	def _on_text_changed(self, event):
		self._dirty = self._textCtrl.GetValue() != self._original_text

	def _on_close(self, event):
		if self._dirty:
			result = gui.messageBox(
				_("You have unsaved changes. Do you want to save before closing?"),
				_("Unsaved Changes"),
				wx.YES_NO | wx.CANCEL | wx.ICON_WARNING,
				self,
			)
			if result == wx.YES:
				self.EndModal(wx.ID_OK)
				return
			elif result == wx.CANCEL:
				return
		self.EndModal(wx.ID_CANCEL)

	def get_text(self):
		return self._textCtrl.GetValue()


class ClipboardHistoryDialog(wx.Dialog):
	"""Main clipboard history browser dialog, similar to Ditto."""

	def __init__(self, parent, history_manager, paste_callback=None, on_destroy=None, initial_group="All", update_last_clip=None):
		super().__init__(
			parent,
			title=_("Clipboard History"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
		)
		self._history = history_manager
		self._paste_callback = paste_callback
		self._on_destroy = on_destroy
		self._initial_group = initial_group
		self._update_last_clip = update_last_clip
		self._filtered_entries = []
		self._build_ui()
		# Set the initial group filter before populating
		self._refresh_group_filter()
		groups = [self._groupFilter.GetString(i) for i in range(self._groupFilter.GetCount())]
		if self._initial_group in groups:
			self._groupFilter.SetStringSelection(self._initial_group)
		query, group = self._get_current_filters()
		self._populate_list(query, group)
		self.SetSize((600, 500))
		self.CentreOnScreen()

	def _build_ui(self):
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		panel = wx.Panel(self)
		sizer = wx.BoxSizer(wx.VERTICAL)

		# Search row
		searchSizer = wx.BoxSizer(wx.HORIZONTAL)
		searchLabel = wx.StaticText(panel, label=_("&Search:"))
		searchSizer.Add(searchLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		self._searchCtrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
		self._searchCtrl.Bind(wx.EVT_TEXT, self._on_filter_changed)
		self._searchCtrl.Bind(wx.EVT_TEXT_ENTER, self._on_paste)
		searchSizer.Add(self._searchCtrl, 1, wx.EXPAND)

		sizer.Add(searchSizer, 0, wx.EXPAND | wx.ALL, 5)

		# History list
		self._listCtrl = wx.ListCtrl(panel, style=wx.LC_REPORT)
		self._listCtrl.InsertColumn(0, _("Clip"), width=380)
		self._listCtrl.InsertColumn(1, _("Group"), width=100)
		self._listCtrl.InsertColumn(2, _("Pinned"), width=60)
		self._listCtrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_paste)
		self._listCtrl.Bind(wx.EVT_KEY_DOWN, self._on_list_key_down)
		self._listCtrl.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self._on_context_menu)
		self._listCtrl.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)
		sizer.Add(self._listCtrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

		# Preview area
		previewLabel = wx.StaticText(panel, label=_("&Preview:"))
		sizer.Add(previewLabel, 0, wx.LEFT | wx.TOP, 5)
		self._previewCtrl = wx.TextCtrl(
			panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP
		)
		sizer.Add(self._previewCtrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
		self._selection_order = []
		self._listCtrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
		self._listCtrl.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_item_deselected)

		# Buttons
		buttonSizer = wx.BoxSizer(wx.HORIZONTAL)

		self._copyBtn = wx.Button(panel, label=_("&Copy to Clipboard"))
		self._copyBtn.Bind(wx.EVT_BUTTON, self._on_copy)
		buttonSizer.Add(self._copyBtn, 0, wx.RIGHT, 5)

		self._editBtn = wx.Button(panel, label=_("&Edit"))
		self._editBtn.Bind(wx.EVT_BUTTON, self._on_edit)
		buttonSizer.Add(self._editBtn, 0, wx.RIGHT, 5)

		self._pinBtn = wx.Button(panel, label=_("Pi&n / Unpin"))
		self._pinBtn.Bind(wx.EVT_BUTTON, self._on_toggle_pin)
		buttonSizer.Add(self._pinBtn, 0, wx.RIGHT, 5)

		self._groupBtn = wx.Button(panel, label=_("Set &Group"))
		self._groupBtn.Bind(wx.EVT_BUTTON, self._on_set_group)
		buttonSizer.Add(self._groupBtn, 0, wx.RIGHT, 5)

		self._clearBtn = wx.Button(panel, label=_("C&lear All"))
		self._clearBtn.Bind(wx.EVT_BUTTON, self._on_clear_all)
		buttonSizer.Add(self._clearBtn, 0, wx.RIGHT, 5)

		self._newGroupBtn = wx.Button(panel, label=_("Ne&w Group"))
		self._newGroupBtn.Bind(wx.EVT_BUTTON, self._on_new_group)
		buttonSizer.Add(self._newGroupBtn, 0, wx.RIGHT, 5)

		self._manageGroupsBtn = wx.Button(panel, label=_("&Manage Groups"))
		self._manageGroupsBtn.Bind(wx.EVT_BUTTON, self._on_manage_groups)
		buttonSizer.Add(self._manageGroupsBtn, 0, wx.RIGHT, 10)

		groupLabel = wx.StaticText(panel, label=_("Gro&up:"))
		buttonSizer.Add(groupLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
		self._groupFilter = wx.Choice(panel, choices=[_("All")])
		self._groupFilter.SetSelection(0)
		self._groupFilter.Bind(wx.EVT_CHOICE, self._on_filter_changed)
		buttonSizer.Add(self._groupFilter, 0, wx.ALIGN_CENTER_VERTICAL)

		sizer.Add(buttonSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

		panel.SetSizer(sizer)
		mainSizer.Add(panel, 1, wx.EXPAND)
		self.SetSizer(mainSizer)

		self.Bind(wx.EVT_CLOSE, self._on_close)
		self.SetEscapeId(wx.ID_NONE)
		self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

	def _refresh_group_filter(self):
		"""Refresh the group filter dropdown choices."""
		current = self._groupFilter.GetStringSelection()
		groups = self._history.get_groups()
		display_groups = [_group_display_name(g) for g in groups]
		choices = [_("All")] + display_groups
		# Map translated display names back to internal names
		self._group_display_to_internal = {_group_display_name(g): g for g in groups}
		self._groupFilter.Set(choices)
		if current in choices:
			self._groupFilter.SetStringSelection(current)
		else:
			self._groupFilter.SetSelection(0)

	def _populate_list(self, search_query="", group_filter=""):
		"""Populate the list control with history entries."""
		self._listCtrl.DeleteAllItems()
		self._refresh_group_filter()

		entries = self._history.get_all()

		# Apply group filter
		if group_filter and group_filter != _("All"):
			internal = self._group_display_to_internal.get(group_filter, group_filter)
			entries = [e for e in entries if e.group == internal]

		# Apply search filter
		if search_query:
			query_lower = search_query.lower()
			entries = [e for e in entries if query_lower in e.text.lower()]

		self._filtered_entries = entries
		self._selection_order = []

		for i, entry in enumerate(self._filtered_entries):
			preview = entry.get_preview()
			if entry.pasted:
				preview = _("Pasted: ") + preview
			index = self._listCtrl.InsertItem(i, preview)
			self._listCtrl.SetItem(index, 1, _group_display_name(entry.group) if entry.group else "")
			pin_text = _("Yes") if entry.pinned else ""
			self._listCtrl.SetItem(index, 2, pin_text)

		if self._filtered_entries:
			self._listCtrl.Select(0)
			self._listCtrl.Focus(0)

		count = len(self._filtered_entries)
		if search_query or (group_filter and group_filter != _("All")):
			ui.message(_("%d results found") % count)

	def _get_selected_entry(self):
		"""Get the currently focused/first selected entry."""
		sel = self._listCtrl.GetFirstSelected()
		if 0 <= sel < len(self._filtered_entries):
			return self._filtered_entries[sel]
		return None

	def _get_selected_entries(self):
		"""Get all selected entries in the order they were selected."""
		selected = set()
		sel = self._listCtrl.GetFirstSelected()
		while sel != -1:
			selected.add(sel)
			sel = self._listCtrl.GetNextSelected(sel)
		ordered = [i for i in self._selection_order if i in selected]
		for i in selected:
			if i not in ordered:
				ordered.append(i)
		entries = []
		for i in ordered:
			if 0 <= i < len(self._filtered_entries):
				entries.append(self._filtered_entries[i])
		return entries

	def _get_current_filters(self):
		"""Return the current search query and group filter."""
		query = self._searchCtrl.GetValue()
		group = self._groupFilter.GetStringSelection()
		return query, group

	def _on_filter_changed(self, event):
		query, group = self._get_current_filters()
		self._populate_list(query, group)

	def _on_item_selected(self, event):
		idx = event.GetIndex()
		if idx not in self._selection_order:
			self._selection_order.append(idx)
		entry = self._get_selected_entry()
		if entry:
			self._previewCtrl.SetValue(entry.text)
		else:
			self._previewCtrl.SetValue("")

	def _on_item_deselected(self, event):
		idx = event.GetIndex()
		if idx in self._selection_order:
			self._selection_order.remove(idx)

	def _on_paste(self, event):
		entries = self._get_selected_entries()
		if not entries:
			return
		combined = "\n".join(e.text for e in entries)
		# Check if entries are file paths (by group or by content)
		is_files = all(
			e.group == FILES_AND_FOLDERS_GROUP or _is_file_path_text(e.text)
			for e in entries
		)
		if is_files:
			file_paths = []
			for e in entries:
				file_paths.extend(e.text.splitlines())
			success = _copy_files_to_clipboard(file_paths)
			if not success:
				api.copyToClip(combined)
		else:
			api.copyToClip(combined)
		# Mark pasted entries and move to top
		pasted_ids = {e.entry_id for e in entries}
		self._history.mark_pasted(pasted_ids)
		# If multiple entries were combined, add the combined text as a new entry
		if len(entries) > 1:
			self._history.add(combined)
		if self._update_last_clip:
			self._update_last_clip(combined)
		# Hide immediately so focus returns to the previous window faster
		self.Hide()
		if self._paste_callback:
			wx.CallLater(30, self._paste_callback)
		# Now destroy
		wx.CallAfter(self.Close)

	def _on_copy(self, event):
		entries = self._get_selected_entries()
		if not entries:
			return
		is_files = all(
			e.group == FILES_AND_FOLDERS_GROUP or _is_file_path_text(e.text)
			for e in entries
		)
		if is_files:
			file_paths = []
			for e in entries:
				file_paths.extend(e.text.splitlines())
			success = _copy_files_to_clipboard(file_paths)
		else:
			combined = "\n".join(e.text for e in entries)
			success = api.copyToClip(combined)
		if success:
			tones.beep(1500, 120)
			count = len(entries)
			if count == 1:
				ui.message(_("Copied to clipboard"))
			else:
				ui.message(_("%d items copied to clipboard") % count)

	def _on_edit(self, event):
		"""Edit the selected entry's text in a full editor."""
		entry = self._get_selected_entry()
		if not entry:
			return
		dlg = ClipEditorDialog(self, entry.text)
		if dlg.ShowModal() == wx.ID_OK:
			new_text = dlg.get_text()
			if new_text != entry.text:
				if self._history.update_text(entry.entry_id, new_text):
					ui.message(_("Clip updated"))
				else:
					ui.message(_("Failed to update clip"))
			query, group = self._get_current_filters()
			self._populate_list(query, group)
		dlg.Destroy()

	def _on_toggle_pin(self, event):
		entries = self._get_selected_entries()
		if not entries:
			return
		for entry in entries:
			self._history.toggle_pin(entry.entry_id)
		count = len(entries)
		if count == 1:
			ui.message(_("Pinned") if entries[0].pinned else _("Unpinned"))
		else:
			ui.message(_("%d items toggled") % count)
		query, group = self._get_current_filters()
		self._populate_list(query, group)

	def _on_set_group(self, event):
		"""Assign selected entries to a group."""
		entries = self._get_selected_entries()
		if not entries:
			return
		existing_groups = self._history.get_groups()
		current = entries[0].group if len(entries) == 1 else ""
		dlg = GroupDialog(self, existing_groups, current_group=current)
		if dlg.ShowModal() == wx.ID_OK:
			group_name = dlg.get_group_name()
			for entry in entries:
				self._history.set_group(entry.entry_id, group_name)
			count = len(entries)
			if group_name:
				ui.message(_("%d item(s) added to group: %s") % (count, group_name))
			else:
				ui.message(_("%d item(s) removed from group") % count)
			query, group = self._get_current_filters()
			self._populate_list(query, group)
		dlg.Destroy()

	def _on_new_group(self, event):
		"""Create a new empty group."""
		dlg = wx.TextEntryDialog(self, _("Enter a name for the new group:"), _("New Group"))
		if dlg.ShowModal() == wx.ID_OK:
			name = dlg.GetValue().strip()
			if not name:
				ui.message(_("Group name cannot be empty"))
			elif self._history.create_group(name):
				ui.message(_("Group created: %s") % name)
				query, group = self._get_current_filters()
				self._populate_list(query, group)
			else:
				ui.message(_("Group '%s' already exists") % name)
		dlg.Destroy()

	def _on_manage_groups(self, event):
		"""Open the manage groups dialog."""
		dlg = ManageGroupsDialog(self, self._history)
		dlg.ShowModal()
		dlg.Destroy()
		query, group = self._get_current_filters()
		self._populate_list(query, group)

	def _on_delete(self, event):
		entries = self._get_selected_entries()
		if not entries:
			return
		for entry in entries:
			self._history.delete(entry.entry_id)
		tones.beep(300, 80)
		count = len(entries)
		if count == 1:
			ui.message(_("Deleted"))
		else:
			ui.message(_("%d items deleted") % count)
		query, group = self._get_current_filters()
		self._populate_list(query, group)

	def _on_clear_all(self, event):
		if gui.messageBox(
			_("Are you sure you want to clear all clipboard history? Pinned items will also be removed."),
			_("Clear Clipboard History"),
			wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
			self,
		) == wx.YES:
			self._history.clear_all()
			self._populate_list()
			ui.message(_("History cleared"))

	def _on_context_menu(self, event):
		"""Show context menu for the selected entry."""
		entry = self._get_selected_entry()
		if not entry:
			return
		menu = wx.Menu()
		paste_item = menu.Append(wx.ID_ANY, _("Paste"))
		copy_item = menu.Append(wx.ID_ANY, _("Copy to Clipboard"))
		edit_item = menu.Append(wx.ID_ANY, _("Edit"))
		menu.AppendSeparator()

		# Save as submenu
		save_menu = wx.Menu()
		save_txt_item = save_menu.Append(wx.ID_ANY, _("Text File (.txt)..."))
		save_doc_item = save_menu.Append(wx.ID_ANY, _("Word Document (.docx)..."))
		menu.AppendSubMenu(save_menu, _("Save As"))

		# Move submenu
		move_menu = wx.Menu()
		top_item = move_menu.Append(wx.ID_ANY, _("Top"))
		bottom_item = move_menu.Append(wx.ID_ANY, _("Bottom"))
		menu.AppendSubMenu(move_menu, _("Move To"))

		menu.AppendSeparator()
		pin_item = menu.Append(wx.ID_ANY, _("Unpin") if entry.pinned else _("Pin"))
		group_item = menu.Append(wx.ID_ANY, _("Set Group"))
		delete_item = menu.Append(wx.ID_ANY, _("Delete"))

		self.Bind(wx.EVT_MENU, self._on_paste, paste_item)
		self.Bind(wx.EVT_MENU, self._on_copy, copy_item)
		self.Bind(wx.EVT_MENU, self._on_edit, edit_item)
		self.Bind(wx.EVT_MENU, lambda e: self._save_as_text(entry), save_txt_item)
		self.Bind(wx.EVT_MENU, lambda e: self._save_as_word(entry), save_doc_item)
		self.Bind(wx.EVT_MENU, lambda e: self._move_to(entry, "top"), top_item)
		self.Bind(wx.EVT_MENU, lambda e: self._move_to(entry, "bottom"), bottom_item)
		self.Bind(wx.EVT_MENU, self._on_toggle_pin, pin_item)
		self.Bind(wx.EVT_MENU, self._on_set_group, group_item)
		self.Bind(wx.EVT_MENU, self._on_delete, delete_item)

		self._listCtrl.PopupMenu(menu)
		menu.Destroy()

	def _get_default_filename(self, entry):
		"""Get a safe default filename from the first line of text."""
		first_line = entry.text.strip().split("\n")[0].strip()
		# Remove characters not allowed in filenames
		safe = re.sub(r'[\\/:*?"<>|]', '', first_line)
		# Truncate to a reasonable length
		safe = safe[:60].strip()
		return safe or "clipboard"

	def _save_as_text(self, entry):
		"""Save entry text to a .txt file."""
		default_name = self._get_default_filename(entry) + ".txt"
		dlg = wx.FileDialog(
			self,
			_("Save as Text File"),
			defaultFile=default_name,
			wildcard=_("Text files (*.txt)|*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
			try:
				with open(path, "w", encoding="utf-8") as f:
					f.write(entry.text)
				ui.message(_("Saved as text file"))
			except Exception:
				ui.message(_("Failed to save file"))
		dlg.Destroy()

	def _save_as_word(self, entry):
		"""Save entry text to a .docx Word file using pure Python (no dependencies)."""
		default_name = self._get_default_filename(entry) + ".docx"
		dlg = wx.FileDialog(
			self,
			_("Save as Word Document"),
			defaultFile=default_name,
			wildcard=_("Word documents (*.docx)|*.docx"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		)
		if dlg.ShowModal() == wx.ID_OK:
			path = dlg.GetPath()
			try:
				self._write_docx(path, entry.text)
				ui.message(_("Saved as Word document"))
			except Exception:
				log.error("Clipboard History: Failed to save Word document", exc_info=True)
				ui.message(_("Failed to save Word document"))
		dlg.Destroy()

	@staticmethod
	def _write_docx(path, text):
		"""Create a minimal .docx file from plain text without external dependencies."""
		content_type = (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
			'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
			'<Default Extension="xml" ContentType="application/xml"/>'
			'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
			'</Types>'
		)
		rels = (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
			'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
			'</Relationships>'
		)
		# Build paragraphs XML
		import xml.sax.saxutils as saxutils
		paragraphs = ""
		for line in text.split("\n"):
			escaped = saxutils.escape(line.rstrip("\r"))
			paragraphs += f'<w:p><w:r><w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'
		document = (
			'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
			'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
			f'<w:body>{paragraphs}</w:body>'
			'</w:document>'
		)
		with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
			zf.writestr("[Content_Types].xml", content_type)
			zf.writestr("_rels/.rels", rels)
			zf.writestr("word/document.xml", document)

	def _move_to(self, entry, position):
		"""Move entry to top or bottom."""
		if self._history.move_to_position(entry.entry_id, position):
			query, group = self._get_current_filters()
			self._populate_list(query, group)
			if position == "top":
				self._listCtrl.Select(0)
				self._listCtrl.Focus(0)
			else:
				last = self._listCtrl.GetItemCount() - 1
				self._listCtrl.Select(last)
				self._listCtrl.Focus(last)
				self._listCtrl.EnsureVisible(last)
			position_label = _("top") if position == "top" else _("bottom")
			ui.message(_("Moved to %s") % position_label)

	def _on_char_hook(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		else:
			event.Skip()

	def _on_close(self, event):
		if self._on_destroy:
			# Pass back the current group filter so it can be remembered
			_, group = self._get_current_filters()
			self._on_destroy(group)
		self.DestroyLater()

	def _on_list_key_down(self, event):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_DELETE:
			self._on_delete(event)
		elif keyCode == ord("A") and event.ControlDown():
			for i in range(self._listCtrl.GetItemCount()):
				self._listCtrl.Select(i)
		elif keyCode == ord("P") and event.ControlDown():
			self._on_toggle_pin(event)
		elif keyCode == ord("G") and event.ControlDown():
			self._on_set_group(event)
		elif keyCode == ord("E") and event.ControlDown():
			self._on_edit(event)
		elif keyCode == wx.WXK_UP and event.ShiftDown():
			self._move_entry(-1)
		elif keyCode == wx.WXK_DOWN and event.ShiftDown():
			self._move_entry(1)
		else:
			event.Skip()

	def _move_entry(self, direction):
		"""Move the focused entry up (-1) or down (+1) in the list."""
		focused = self._listCtrl.GetFocusedItem()
		if focused < 0:
			return
		new_pos = focused + direction
		if new_pos < 0 or new_pos >= len(self._filtered_entries):
			return
		# Swap in the underlying history
		entry_a = self._filtered_entries[focused]
		entry_b = self._filtered_entries[new_pos]
		all_entries = self._history.get_all()
		try:
			idx_a = next(i for i, e in enumerate(all_entries) if e.entry_id == entry_a.entry_id)
			idx_b = next(i for i, e in enumerate(all_entries) if e.entry_id == entry_b.entry_id)
		except StopIteration:
			return
		if self._history.swap_entries(idx_a, idx_b):
			query, group = self._get_current_filters()
			self._populate_list(query, group)
			self._listCtrl.Select(new_pos)
			self._listCtrl.Focus(new_pos)
			self._listCtrl.EnsureVisible(new_pos)


class _ClipboardListenerWindow(windowUtils.CustomWindow):
	"""Invisible Win32 window that receives WM_CLIPBOARDUPDATE messages."""
	className = "NVDAClipboardHistoryListener"

	def __init__(self, callback):
		super().__init__("NVDA Clipboard Listener")
		self._callback = callback

	def windowProc(self, hwnd, msg, wParam, lParam):
		if msg == WM_CLIPBOARDUPDATE:
			try:
				wx.CallAfter(self._callback)
			except Exception:
				pass


def _destroy_listener_window(window):
	"""Safely destroy the listener window."""
	try:
		window.destroy()
	except Exception:
		pass


class ClipboardHistorySettingsPanel(SettingsPanel):
	"""Settings panel for Clipboard History in NVDA settings."""

	title = _("Clipboard History")

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

		self.maxEntriesCtrl = helper.addLabeledControl(
			_("&Maximum number of history entries:"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=MIN_MAX_ENTRIES,
			max=MAX_MAX_ENTRIES,
			initial=config.conf[CONFIG_SECTION]["maxEntries"],
		)

		self.persistHistoryCB = helper.addItem(
			wx.CheckBox(self, label=_("&Save history between NVDA sessions"))
		)
		self.persistHistoryCB.SetValue(config.conf[CONFIG_SECTION]["persistHistory"])

		self.announceNewCB = helper.addItem(
			wx.CheckBox(self, label=_("&Announce when new text is copied"))
		)
		self.announceNewCB.SetValue(config.conf[CONFIG_SECTION]["announceNew"])

	def onSave(self):
		config.conf[CONFIG_SECTION]["maxEntries"] = self.maxEntriesCtrl.GetValue()
		config.conf[CONFIG_SECTION]["persistHistory"] = self.persistHistoryCB.GetValue()
		config.conf[CONFIG_SECTION]["announceNew"] = self.announceNewCB.GetValue()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Clipboard History")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		log.debug("Clipboard History: GlobalPlugin __init__ starting")

		# Register config
		confspec = {
			"maxEntries": f"integer(default={DEFAULT_MAX_ENTRIES}, min={MIN_MAX_ENTRIES}, max={MAX_MAX_ENTRIES})",
			"persistHistory": "boolean(default=True)",
			"announceNew": "boolean(default=False)",
		}
		config.conf.spec[CONFIG_SECTION] = confspec

		# Register settings panel
		NVDASettingsDialog.categoryClasses.append(ClipboardHistorySettingsPanel)

		# Initialize history manager
		self._history = ClipboardHistoryManager(
			max_entries=config.conf[CONFIG_SECTION]["maxEntries"]
		)

		# Navigation position for cycling through history
		self._nav_pos = -1

		# Clipboard monitoring
		self._last_clip_text = ""
		self._clipboard_listener_registered = False
		self._dialog = None
		self._last_group_filter = _("All")

		# Ensure the built-in group exists
		self._history.create_group(FILES_AND_FOLDERS_GROUP)

		# Start monitoring
		self._start_monitoring()
		log.debug("Clipboard History: GlobalPlugin __init__ complete")

	def terminate(self, *args, **kwargs):
		super().terminate(*args, **kwargs)
		self._stop_monitoring()
		NVDASettingsDialog.categoryClasses.remove(ClipboardHistorySettingsPanel)

	def _start_monitoring(self):
		"""Register as a clipboard format listener for instant change notifications."""
		try:
			self._last_clip_text = api.getClipData()
		except Exception:
			self._last_clip_text = ""
		# Create an invisible Win32 window to receive WM_CLIPBOARDUPDATE
		self._clip_window = _ClipboardListenerWindow(self._on_clipboard_changed)
		hwnd = self._clip_window.handle
		if ctypes.windll.user32.AddClipboardFormatListener(hwnd):
			self._clipboard_listener_registered = True
			log.debug("Clipboard History: Registered clipboard format listener")
		else:
			log.warning("Clipboard History: AddClipboardFormatListener failed, falling back to polling")
			self._clipboard_listener_registered = False
			self._monitor_timer = wx.CallLater(DEFAULT_POLL_INTERVAL, self._poll_clipboard)

	def _stop_monitoring(self):
		"""Remove the clipboard format listener."""
		if self._clipboard_listener_registered and hasattr(self, '_clip_window') and self._clip_window:
			hwnd = self._clip_window.handle
			ctypes.windll.user32.RemoveClipboardFormatListener(hwnd)
			self._clipboard_listener_registered = False
			log.debug("Clipboard History: Removed clipboard format listener")
		if hasattr(self, '_clip_window') and self._clip_window:
			_destroy_listener_window(self._clip_window)
			self._clip_window = None
		if hasattr(self, '_monitor_timer') and self._monitor_timer:
			self._monitor_timer.Stop()
			self._monitor_timer = None

	def _on_clipboard_changed(self):
		"""Handle clipboard change event."""
		try:
			current_text = api.getClipData()
		except Exception:
			current_text = ""

		# Always check for copied files/folders (CF_HDROP)
		try:
			file_paths = _get_clipboard_file_paths()
			if file_paths:
				current_text = "\n".join(file_paths)
		except Exception:
			log.error("Clipboard History: Error reading CF_HDROP", exc_info=True)

		if current_text and current_text != self._last_clip_text:
			self._last_clip_text = current_text
			was_added = self._history.add(current_text)
			self._nav_pos = -1

			if was_added and config.conf[CONFIG_SECTION]["announceNew"]:
				preview = current_text[:50].replace("\n", " ")
				ui.message(_("Clipboard: %s") % preview)

	def _poll_clipboard(self):
		"""Fallback polling method if event-driven approach fails."""
		self._on_clipboard_changed()
		if hasattr(self, '_monitor_timer') and self._monitor_timer:
			self._monitor_timer.Restart(DEFAULT_POLL_INTERVAL)

	def _simulate_paste(self):
		"""Simulate Ctrl+V to paste."""
		import keyboardHandler

		gesture = keyboardHandler.KeyboardInputGesture.fromName("control+v")
		gesture.send()

	@script(
		# Translators: Description of the command to open the clipboard history dialog
		description=_("Show the clipboard history dialog to browse, search and paste previous clipboard entries"),
		gesture="kb:NVDA+a",
	)
	def script_showHistory(self, gesture):
		# If dialog is already open, just bring it to front
		if self._dialog is not None:
			self._dialog.Raise()
			self._dialog.SetFocus()
			return

		if self._history.count == 0:
			ui.message(_("Clipboard history is empty"))
			return

		def _show():
			try:
				log.debug("Clipboard History: Opening dialog")
				gui.mainFrame.prePopup()
				self._dialog = ClipboardHistoryDialog(
					gui.mainFrame,
					self._history,
					paste_callback=self._simulate_paste,
					on_destroy=self._on_dialog_destroyed,
					initial_group=self._last_group_filter,
					update_last_clip=self._set_last_clip_text,
				)
				self._dialog.Show()
				gui.mainFrame.postPopup()
				log.debug("Clipboard History: Dialog opened successfully")
			except Exception:
				log.error("Clipboard History: Failed to open dialog", exc_info=True)
				gui.mainFrame.postPopup()

		wx.CallAfter(_show)

	def _on_dialog_destroyed(self, last_group=None):
		self._last_group_filter = last_group or _("All")
		self._dialog = None

	def _set_last_clip_text(self, text):
		"""Update the last clipboard text so the poller doesn't re-detect it."""
		self._last_clip_text = text

	@script(
		# Translators: Description of the command to navigate to the previous clipboard entry
		description=_("Navigate to the previous item in clipboard history and announce it"),
		gesture="kb:NVDA+alt+upArrow",
	)
	def script_previousEntry(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		self._nav_pos += 1
		if self._nav_pos >= len(entries):
			self._nav_pos = len(entries) - 1
			tones.beep(200, 100)
			ui.message(_("End of clipboard history"))
			return

		entry = entries[self._nav_pos]
		preview = entry.get_preview(120)
		ui.message(_("%d of %d: %s") % (self._nav_pos + 1, len(entries), preview))

	@script(
		# Translators: Description of the command to navigate to the next clipboard entry
		description=_("Navigate to the next item in clipboard history and announce it"),
		gesture="kb:NVDA+alt+downArrow",
	)
	def script_nextEntry(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		self._nav_pos -= 1
		if self._nav_pos < 0:
			self._nav_pos = 0
			tones.beep(200, 100)
			ui.message(_("Beginning of clipboard history"))
			return

		entry = entries[self._nav_pos]
		preview = entry.get_preview(120)
		ui.message(_("%d of %d: %s") % (self._nav_pos + 1, len(entries), preview))

	@script(
		# Translators: Description of the command to paste the navigated clipboard entry
		description=_("Paste the currently navigated clipboard history entry"),
		gesture="kb:NVDA+alt+v",
	)
	def script_pasteEntry(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		pos = max(self._nav_pos, 0)
		if pos >= len(entries):
			pos = 0

		entry = entries[pos]
		is_file = entry.group == FILES_AND_FOLDERS_GROUP or _is_file_path_text(entry.text)
		if is_file:
			file_paths = entry.text.splitlines()
			success = _copy_files_to_clipboard(file_paths)
		else:
			success = api.copyToClip(entry.text)
		if success:
			self._last_clip_text = entry.text
			self._nav_pos = -1
			wx.CallLater(50, self._simulate_paste)
			tones.beep(1500, 80)
		else:
			ui.message(_("Failed to paste"))

	@script(
		# Translators: Description of the command to copy the navigated entry to clipboard
		description=_("Copy the currently navigated clipboard history entry to the clipboard without pasting"),
		gesture="kb:NVDA+alt+enter",
	)
	def script_copyEntry(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		pos = max(self._nav_pos, 0)
		if pos >= len(entries):
			pos = 0

		entry = entries[pos]
		is_file = entry.group == FILES_AND_FOLDERS_GROUP or _is_file_path_text(entry.text)
		if is_file:
			file_paths = entry.text.splitlines()
			success = _copy_files_to_clipboard(file_paths)
		else:
			success = api.copyToClip(entry.text)
		if success:
			self._last_clip_text = entry.text
			tones.beep(1500, 120)
			ui.message(_("Copied to clipboard"))
		else:
			ui.message(_("Failed to copy"))

	@script(
		# Translators: Description of the command to delete the navigated clipboard entry
		description=_("Delete the currently navigated clipboard history entry"),
		gesture="kb:NVDA+alt+delete",
	)
	def script_deleteEntry(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		pos = max(self._nav_pos, 0)
		if pos >= len(entries):
			pos = 0

		entry = entries[pos]
		self._history.delete(entry.entry_id)
		tones.beep(300, 80)
		ui.message(_("Deleted"))

		remaining = self._history.get_all()
		if not remaining:
			self._nav_pos = -1
		elif self._nav_pos >= len(remaining):
			self._nav_pos = len(remaining) - 1

	@script(
		# Translators: Description of the command to pin/unpin the navigated clipboard entry
		description=_("Pin or unpin the currently navigated clipboard history entry"),
		gesture="kb:NVDA+alt+p",
	)
	def script_togglePin(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		pos = max(self._nav_pos, 0)
		if pos >= len(entries):
			pos = 0

		entry = entries[pos]
		is_pinned = self._history.toggle_pin(entry.entry_id)
		ui.message(_("Pinned") if is_pinned else _("Unpinned"))

	@script(
		# Translators: Description of the command to clear clipboard history
		description=_("Clear all unpinned entries from clipboard history"),
		gesture="kb:NVDA+alt+x",
	)
	def script_clearHistory(self, gesture):
		if self._history.count == 0:
			ui.message(_("Clipboard history is already empty"))
			return
		self._history.clear_unpinned()
		self._nav_pos = -1
		tones.beep(400, 150)
		ui.message(_("Clipboard history cleared. Pinned items kept."))

	@script(
		# Translators: Description of the command to announce current clipboard content
		description=_("Announce the current clipboard content. Press twice to show in a browsable message"),
		gesture="kb:NVDA+c",
	)
	def script_announceClipboard(self, gesture):
		try:
			text = api.getClipData()
		except Exception:
			text = ""
		if not text:
			ui.message(_("Clipboard is empty"))
			return
		if getLastScriptRepeatCount() >= 1:
			ui.browseableMessage(text, _("Clipboard Content"))
		else:
			preview = text[:200].replace("\n", " ")
			ui.message(preview)

	@script(
		# Translators: Description of the command to set or change the group for the navigated entry
		description=_("Set or change the group for the currently navigated clipboard entry"),
		gesture="kb:NVDA+alt+g",
	)
	def script_setGroup(self, gesture):
		entries = self._history.get_all()
		if not entries:
			ui.message(_("Clipboard history is empty"))
			return

		pos = max(self._nav_pos, 0)
		if pos >= len(entries):
			pos = 0

		entry = entries[pos]

		def _show():
			gui.mainFrame.prePopup()
			existing_groups = self._history.get_groups()
			dlg = GroupDialog(gui.mainFrame, existing_groups, current_group=entry.group)
			if dlg.ShowModal() == wx.ID_OK:
				group_name = dlg.get_group_name()
				self._history.set_group(entry.entry_id, group_name)
				if group_name:
					ui.message(_("Added to group: %s") % group_name)
				else:
					ui.message(_("Removed from group"))
			dlg.Destroy()
			gui.mainFrame.postPopup()

		wx.CallAfter(_show)

	@script(
		# Translators: Description of the command to append selected text to the latest clipboard entry
		description=_("Append selected text to the latest clipboard entry"),
		gesture="kb:NVDA+shift+a",
	)
	def script_appendToClipboard(self, gesture):
		import browseMode
		import textInfos
		# Get the selected text
		obj = api.getFocusObject()
		treeInterceptor = obj.treeInterceptor
		if isinstance(treeInterceptor, browseMode.BrowseModeDocumentTreeInterceptor):
			obj = treeInterceptor
		try:
			info = obj.makeTextInfo(textInfos.POSITION_SELECTION)
			if not info or info.isCollapsed:
				ui.message(_("No text selected"))
				return
			newText = info.clipboardText
		except Exception:
			ui.message(_("No text selected"))
			return
		if not newText:
			ui.message(_("No text selected"))
			return
		# Get existing clipboard text
		try:
			clipData = api.getClipData()
		except Exception:
			clipData = ""
		if clipData:
			combined = clipData + "\n" + newText
		else:
			combined = newText
		api.copyToClip(combined)
		self._last_clip_text = combined
		self._history.add(combined)
		ui.message(_("Appended"))

	@script(
		# Translators: Description of the command to open a blank editor to create a new clip
		description=_("Open an editor to write a new clip and save it to clipboard history"),
		gesture="kb:NVDA+shift+c",
	)
	def script_newClip(self, gesture):
		def _show():
			gui.mainFrame.prePopup()
			dlg = ClipEditorDialog(gui.mainFrame, "", title=_("New Clip"))
			if dlg.ShowModal() == wx.ID_OK:
				new_text = dlg.get_text()
				if new_text and new_text.strip():
					self._history.add(new_text)
					api.copyToClip(new_text)
					self._last_clip_text = new_text
					ui.message(_("Clip saved"))
			dlg.Destroy()
			gui.mainFrame.postPopup()

		wx.CallAfter(_show)
