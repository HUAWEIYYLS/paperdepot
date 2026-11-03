#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文库导入器 — 图形化导入入口

双击本文件（或运行 启动导入器.cmd）即可打开窗口：
  · 选 PDF → 走完整进件流水线（MinerU 解析 → 元数据 → 组装条目 → 写入 vault）
  · 从 Zotero storage 批量导入（按篇数限额）
  · 导入完成后自动重建 _index.md / _stats.md
  · 实时显示流水线日志

底层就是 tools/ingest.py 与 tools/make_index.py，没有另写一套逻辑。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _paths

DEFAULT_VAULT = _paths.default_vault()
PY = sys.executable
STATE = os.path.join(ROOT, 'cache', 'gui_state.json')


def load_state():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.proc = None
        self.running = False
        st = load_state()

        root.title('论文库导入器')
        root.geometry('860x620')
        root.minsize(720, 480)

        pad = {'padx': 10, 'pady': 6}

        # ---- 顶部：库路径 ----
        top = tk.Frame(root)
        top.pack(fill='x', **pad)
        tk.Label(top, text='库路径（vault）:').pack(side='left')
        self.vault_var = tk.StringVar(value=st.get('vault') or DEFAULT_VAULT)
        tk.Entry(top, textvariable=self.vault_var).pack(
            side='left', fill='x', expand=True, padx=6)
        tk.Button(top, text='选择…', command=self.choose_vault).pack(side='left')

        # ---- 按钮区 ----
        bar = tk.Frame(root)
        bar.pack(fill='x', **pad)
        self.btn_pdf = tk.Button(bar, text='选择 PDF 并导入',
                                 command=self.pick_pdfs, height=2, width=18)
        self.btn_pdf.pack(side='left')
        self.btn_storage = tk.Button(bar, text='从 Zotero 批量导入',
                                     command=self.from_storage, height=2, width=18)
        self.btn_storage.pack(side='left', padx=8)
        tk.Label(bar, text='限额').pack(side='left')
        self.limit_var = tk.StringVar(value=str(st.get('limit', 5)))
        tk.Spinbox(bar, from_=1, to=50, width=4,
                   textvariable=self.limit_var).pack(side='left', padx=4)
        self.btn_index = tk.Button(bar, text='重建索引', command=self.rebuild_index)
        self.btn_index.pack(side='left', padx=8)
        self.btn_open = tk.Button(bar, text='打开库文件夹', command=self.open_vault)
        self.btn_open.pack(side='left')

        # ---- 进度 ----
        pf = tk.Frame(root)
        pf.pack(fill='x', **pad)
        self.pb = ttk.Progressbar(pf, mode='determinate', maximum=100)
        self.pb.pack(side='left', fill='x', expand=True)
        self.status = tk.Label(pf, text='空闲', width=22, anchor='w')
        self.status.pack(side='left', padx=8)

        # ---- 日志 ----
        lf = tk.Frame(root)
        lf.pack(fill='both', expand=True, padx=10, pady=(0, 4))
        self.log = ScrolledText(lf, height=20, state='disabled',
                                font=('Microsoft YaHei UI', 9), wrap='word')
        self.log.pack(fill='both', expand=True)

        # ---- 底部提示 ----
        tip = ('提示：每篇约 30–90 秒（MinerU 云端解析，消耗 API 配额）；'
               '已入库的同一 PDF 会按指纹跳过。')
        tk.Label(root, text=tip, anchor='w', fg='#666').pack(fill='x', padx=10, pady=(0, 8))

        # 日志轮询
        self.root.after(120, self.drain)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    # ---------- 基础动作 ----------
    def choose_vault(self):
        d = filedialog.askdirectory(title='选择 Obsidian vault')
        if d:
            self.vault_var.set(os.path.normpath(d))
            save_state({'vault': self.vault_var.get()})

    def open_vault(self):
        v = self.vault_var.get()
        if os.path.isdir(v):
            os.startfile(v)
        else:
            messagebox.showerror('路径不存在', v)

    def write(self, s):
        self.log.configure(state='normal')
        self.log.insert('end', s + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def set_busy(self, busy):
        self.running = busy
        state = 'disabled' if busy else 'normal'
        for b in (self.btn_pdf, self.btn_storage, self.btn_index):
            b.configure(state=state)
        self.pb.configure(mode='indeterminate' if busy else 'determinate')
        if busy:
            self.pb.start(12)
            self.status.configure(text='导入中…')
        else:
            self.pb.stop()
            self.pb['value'] = 0
            self.status.configure(text='空闲')

    # ---------- 运行流水线 ----------
    def run(self, title, args, then_index=True):
        if self.running:
            messagebox.showinfo('正在运行', '当前有任务在跑，等它结束。')
            return
        vault = self.vault_var.get().strip()
        if not os.path.isdir(vault):
            messagebox.showerror('库不存在', vault)
            return
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.write(f'▶ {title}')
        self.write(f'  库: {vault}')
        self.set_busy(True)
        t = threading.Thread(target=self._worker, args=(args, vault, then_index),
                             daemon=True)
        t.start()

    def _worker(self, args, vault, then_index):
        # 注意：本函数跑在后台线程，绝不能直接碰 Tk 控件；
        # 所有输出通过 queue 交给主线程的 drain() 去写。
        try:
            cmd = [PY, os.path.join(HERE, 'ingest.py')] + list(args) + ['--vault', vault]
            self._spawn(cmd, cwd=ROOT)
            if then_index:
                self.q.put(('log', ''))
                self.q.put(('log', '— 重建索引 —'))
                self._spawn([PY, os.path.join(HERE, 'make_index.py'), '--vault', vault],
                            cwd=ROOT)
            self.q.put(('done', None))
        except Exception as exc:                     # noqa: BLE001
            self.q.put(('error', f'{type(exc).__name__}: {exc}'))

    def _spawn(self, cmd, cwd):
        self.q.put(('log', '$ ' + ' '.join(f'"{c}"' if ' ' in c else c for c in cmd[1:])))
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True,
                             encoding='utf-8', errors='replace', bufsize=1,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.proc = p
        for line in p.stdout:
            self.q.put(('log', line.rstrip()))
        p.wait()
        self.proc = None
        if p.returncode not in (0, 1, 2):
            raise RuntimeError(f'退出码 {p.returncode}')

    def drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == 'log':
                    self.write(payload)
                elif kind == 'done':
                    self.set_busy(False)
                    self.status.configure(text='完成')
                    self.write('\\n✅ 任务结束')
                elif kind == 'error':
                    self.set_busy(False)
                    self.status.configure(text='出错')
                    self.write('\\n❌ ' + payload)
        except queue.Empty:
            pass
        self.root.after(120, self.drain)

    # ---------- 业务按钮 ----------
    def pick_pdfs(self):
        files = filedialog.askopenfilenames(
            title='选择要导入的 PDF（可多选）',
            filetypes=[('PDF', '*.pdf'), ('所有文件', '*.*')])
        if not files:
            return
        self.run(f'导入 {len(files)} 个 PDF', list(files))

    def from_storage(self):
        try:
            n = int(self.limit_var.get())
        except ValueError:
            n = 5
        save_state({'vault': self.vault_var.get(), 'limit': n})
        if not messagebox.askyesno(
                '从 Zotero 批量导入',
                f'从 Zotero storage 取前 {n} 篇 PDF 导入。\\n'
                f'已入库的会自动跳过，但仍建议限量。继续？'):
            return
        self.run(f'Zotero storage 批量导入（最多 {n} 篇）',
                 ['--from-storage', '--limit', str(n)], then_index=True)

    def rebuild_index(self):
        vault = self.vault_var.get().strip()
        if not os.path.isdir(vault):
            messagebox.showerror('库不存在', vault)
            return
        self.set_busy(True)
        self.write('▶ 重建索引')

        def job():
            try:
                p = subprocess.run([PY, os.path.join(HERE, 'make_index.py'),
                                    '--vault', vault], cwd=ROOT,
                                   capture_output=True, text=True,
                                   encoding='utf-8', errors='replace',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                for line in (p.stdout or '').splitlines():
                    self.q.put(('log', line))
                self.q.put(('done', None))
            except Exception as exc:                 # noqa: BLE001
                self.q.put(('error', f'{type(exc).__name__}: {exc}'))

        threading.Thread(target=job, daemon=True).start()

    def on_close(self):
        if self.running:
            if not messagebox.askyesno('正在导入', '任务还在跑，确定关闭？'):
                return
        save_state({'vault': self.vault_var.get(), 'limit': self.limit_var.get()})
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
