"""KiLibEdit desktop application (Python standard library only)."""
import csv
import io
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from library import Library, atomic_save


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('KiLibEdit — KiCad シンボル一括編集')
        self.geometry('1280x760')
        self.minsize(800, 450)
        self.lib = None
        self.path = None
        self.original = None
        self.undo_stack, self.redo_stack = [], []
        self.active_column = 'Value'
        self.editor = None
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill='x')
        for label, action in [('開く', self.open), ('保存', self.save), ('名前を付けて保存', lambda: self.save(True)), ('元に戻す', self.undo), ('やり直す', self.redo), ('列を追加', self.add_column), ('一括設定', self.bulk), ('コピー', self.copy), ('貼り付け', self.paste)]:
            ttk.Button(bar, text=label, command=action).pack(side='left', padx=2)
        search = ttk.Frame(self, padding=(10, 0, 10, 8))
        search.pack(fill='x')
        ttk.Label(search, text='検索（全列）').pack(side='left')
        self.query = tk.StringVar()
        ttk.Entry(search, textvariable=self.query, width=35).pack(side='left', padx=8)
        self.query.trace_add('write', lambda *_: self.refresh())
        ttk.Label(search, text='セルをダブルクリックで編集 ／ Shift・Ctrlで複数行選択').pack(side='left')
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=10)
        self.table = ttk.Treeview(frame, show='headings', selectmode='extended')
        ys = ttk.Scrollbar(frame, orient='vertical', command=self.table.yview)
        xs = ttk.Scrollbar(frame, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        ys.grid(row=0, column=1, sticky='ns')
        xs.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.table.tag_configure('changed', background='#fff0ca')
        self.table.bind('<Double-1>', self.edit)
        self.table.bind('<Button-1>', self.click)
        self.status = tk.StringVar(value='「開く」から .kicad_sym ファイルを選択してください')
        ttk.Label(self, textvariable=self.status, padding=10).pack(fill='x')
        for key, action in [('<Control-o>', self.open), ('<Control-s>', self.save), ('<Control-z>', self.undo), ('<Control-y>', self.redo), ('<Control-c>', self.copy), ('<Control-v>', self.paste)]:
            self.bind(key, lambda e, fn=action: fn() if not isinstance(e.widget, (ttk.Entry, tk.Entry)) else None)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def commit_editor(self):
        if self.editor:
            self.editor_commit()

    def discard_ok(self):
        self.commit_editor()
        return not self.lib or not self.lib.changes or messagebox.askyesno('未保存の編集', '未保存の変更を破棄しますか？')

    def open(self, path=None):
        if not self.discard_ok():
            return
        path = path or filedialog.askopenfilename(filetypes=[('KiCad symbol library', '*.kicad_sym')])
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            lib = Library(raw.decode('utf-8'))
            self.lib, self.path, self.original = lib, Path(path), raw
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.query.set('')
            self.configure_columns()
            self.refresh()
        except Exception as exc:
            messagebox.showerror('読み込みエラー', str(exc))

    def configure_columns(self):
        self.cols = ['Symbol', 'Extends'] + self.lib.columns
        self.table.configure(columns=self.cols)
        for key in self.cols:
            self.table.heading(key, text=key, command=lambda k=key: self.sort(k))
            self.table.column(key, width=180, minwidth=90, stretch=False)

    def refresh(self):
        if not self.lib:
            return
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        query = self.query.get().casefold()
        changed_rows = {r for r, _ in self.lib.changes}
        for row, name in enumerate(self.lib.names):
            values = [name, self.lib.parents[row]] + [self.lib.get(row, k) for k in self.lib.columns]
            if query in '\t'.join(values).casefold():
                self.table.insert('', 'end', iid=str(row), values=values, tags=('changed',) if row in changed_rows else ())
        self.table.selection_set([i for i in selected if self.table.exists(i)])
        self.title(f'{"* " if self.lib.changes else ""}{self.path.name} — KiLibEdit')
        self.status.set(f'{self.path}  |  表示 {len(self.table.get_children())} / {len(self.lib.names)} 件  |  変更 {len(self.lib.changes)} セル  |  操作列: {self.active_column}')

    def sort(self, key):
        self.commit_editor()
        rows = sorted(self.table.get_children(), key=lambda i: self.table.set(i, key).casefold())
        if rows == list(self.table.get_children()):
            rows.reverse()
        for pos, row in enumerate(rows):
            self.table.move(row, '', pos)

    def click(self, event):
        self.commit_editor()
        col = self.table.identify_column(event.x)
        if col and self.lib:
            self.active_column = self.cols[int(col[1:]) - 1]

    def edit(self, event):
        if not self.lib:
            return
        row = self.table.identify_row(event.y)
        col = self.table.identify_column(event.x)
        if not row or not col:
            return
        key = self.cols[int(col[1:]) - 1]
        if key in ('Symbol', 'Extends'):
            return
        box = self.table.bbox(row, col)
        if not box:
            return
        entry = ttk.Entry(self.table)
        self.editor = entry
        entry.place(x=box[0], y=box[1], width=box[2], height=box[3])
        entry.insert(0, self.lib.get(int(row), key))
        entry.select_range(0, 'end')
        entry.focus_set()
        def finish(save=True):
            if self.editor is not entry:
                return
            value = entry.get()
            self.editor = None
            entry.destroy()
            if save:
                self.apply([(int(row), key, value)])
        self.editor_commit = finish
        entry.bind('<Return>', lambda e: finish())
        entry.bind('<Escape>', lambda e: finish(False))
        entry.bind('<FocusOut>', lambda e: finish())

    def apply(self, changes):
        before = self.lib.changes.copy()
        for row, key, value in changes:
            self.lib.set(row, key, value)
        if before != self.lib.changes:
            self.undo_stack.append(before)
            self.redo_stack.clear()
        self.refresh()

    def undo(self):
        self.commit_editor()
        if self.lib and self.undo_stack:
            self.redo_stack.append(self.lib.changes.copy())
            self.lib.changes = self.undo_stack.pop()
            self.refresh()

    def redo(self):
        self.commit_editor()
        if self.lib and self.redo_stack:
            self.undo_stack.append(self.lib.changes.copy())
            self.lib.changes = self.redo_stack.pop()
            self.refresh()

    def add_column(self):
        if not self.lib:
            return
        key = simpledialog.askstring('列を追加', '独自プロパティ名:')
        if key and key.strip() and key not in self.cols:
            self.lib.columns.append(key)
            self.configure_columns()
            self.refresh()

    def bulk(self):
        self.commit_editor()
        rows = self.table.selection()
        if not rows or self.active_column in ('Symbol', 'Extends'):
            messagebox.showinfo('一括設定', '編集する列のセルをクリックし、対象行を選択してください。')
            return
        value = simpledialog.askstring('一括設定', f'{len(rows)} 行の {self.active_column} に設定する値（空欄で値を消去）:')
        if value is not None:
            self.apply([(int(r), self.active_column, value) for r in rows])

    def copy(self):
        if not self.lib:
            return
        rows = set(self.table.selection())
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, delimiter='\t', lineterminator='\r\n')
        start = self.cols.index(self.active_column)
        for row in self.table.get_children():
            if row in rows:
                writer.writerow([self.table.set(row, k) for k in self.cols[start:]])
        self.clipboard_clear()
        self.clipboard_append(stream.getvalue())

    def paste(self):
        self.commit_editor()
        if not self.lib or not self.table.selection():
            return
        try:
            matrix = list(csv.reader(io.StringIO(self.clipboard_get(), newline=''), delimiter='\t'))
            visible = list(self.table.get_children())
            selected = set(self.table.selection())
            start_row = next(i for i, r in enumerate(visible) if r in selected)
            start_col = self.cols.index(self.active_column)
            if start_col < 2:
                raise ValueError('SymbolとExtendsは読み取り専用です。プロパティ列を選択してください。')
            if start_row + len(matrix) > len(visible) or any(start_col + len(r) > len(self.cols) for r in matrix):
                raise ValueError('貼り付け範囲が表を超えています。必要に応じて列を追加してください。')
            self.apply([(int(visible[start_row + y]), self.cols[start_col + x], value) for y, row in enumerate(matrix) for x, value in enumerate(row)])
        except Exception as exc:
            messagebox.showerror('貼り付けエラー', str(exc))

    def save(self, save_as=False):
        self.commit_editor()
        if not self.lib:
            return
        path = filedialog.asksaveasfilename(defaultextension='.kicad_sym', initialfile=self.path.name, filetypes=[('KiCad symbol library', '*.kicad_sym')]) if save_as else self.path
        if not path:
            return
        try:
            text = self.lib.render()
            same = Path(path).resolve() == self.path.resolve()
            backup = atomic_save(path, text, self.original if same else None)
            columns = self.lib.columns[:]
            self.lib = Library(text)
            self.lib.columns = columns
            self.path, self.original = Path(path), text.encode('utf-8')
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.refresh()
            self.status.set(f'保存しました: {path}' + (f'  |  バックアップ: {backup.name}' if backup else ''))
        except Exception as exc:
            messagebox.showerror('保存エラー', str(exc))

    def close(self):
        if self.discard_ok():
            self.destroy()


if __name__ == '__main__':
    app = App()
    if len(sys.argv) > 1:
        app.open(sys.argv[1])
    app.mainloop()
