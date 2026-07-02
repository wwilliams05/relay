"""Relay launcher — a tiny desktop window so the whole flow runs without the terminal.

Vision (kept deliberately simple): import your resume, type what you're looking for,
press Run. Relay discovers matching internships and opens the spreadsheet; you check
which jobs to pursue there, come back and press step 2 to find people at those
companies. Everything else lives in the spreadsheet.

Built on tkinter (Python's stdlib GUI) so there's nothing extra to install. Long
operations run on a background thread; the window stays responsive and reports status.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config, flow


class RelayApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.resume_path: str | None = None
        self._busy = False
        # Worker threads hand results back through this queue; only the main thread
        # (via _poll_results) touches Tk — cross-thread Tk calls are not safe.
        self._results: queue.Queue = queue.Queue()
        root.title("Relay")
        root.minsize(520, 340)

        pad = {"padx": 14, "pady": 6}
        frm = ttk.Frame(root)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Relay", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(frm, text="Find internships & warm intros — it prepares, you approve.",
                  foreground="#666").grid(row=1, column=0, columnspan=3, sticky="w", padx=14)

        # Resume
        ttk.Label(frm, text="Résumé:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Button(frm, text="Import PDF…", command=self.pick_resume).grid(
            row=2, column=1, sticky="w", **pad)
        self.resume_label = ttk.Label(frm, text="(using saved profile if none)", foreground="#888")
        self.resume_label.grid(row=2, column=2, sticky="w", **pad)

        # Notes
        ttk.Label(frm, text="Looking for:").grid(row=3, column=0, sticky="w", **pad)
        self.notes = ttk.Entry(frm)
        self.notes.insert(0, "Fall 2026 Co-Op, Product Management or BizOps")
        self.notes.grid(row=3, column=1, columnspan=2, sticky="ew", **pad)
        self.notes.bind("<Return>", lambda _e: self.run_discover())

        # Actions
        actions = ttk.Frame(frm)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(12, 4))
        self.btn_discover = ttk.Button(
            actions, text="①  Find jobs  ▶", command=self.run_discover)
        self.btn_discover.pack(side="left", padx=4)
        self.btn_people = ttk.Button(
            actions, text="②  Find people for checked jobs", command=self.run_find_checked)
        self.btn_people.pack(side="left", padx=4)
        self.btn_save = ttk.Button(actions, text="Save", command=self.run_save)
        self.btn_save.pack(side="left", padx=4)
        self.btn_open = ttk.Button(actions, text="Open spreadsheet", command=self.open_sheet)
        self.btn_open.pack(side="left", padx=4)

        draft = ttk.Button(frm, text="③  Draft outreach for checked contacts  (coming in M2)",
                           state="disabled")
        draft.grid(row=5, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 6))

        # Status
        self.status = tk.StringVar(value="Ready.")
        ttk.Separator(frm).grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=4)
        ttk.Label(frm, textvariable=self.status, foreground="#333").grid(
            row=7, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 4))
        self.progress = ttk.Progressbar(frm, mode="indeterminate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 12))

        self._poll_results()  # start the main-thread result pump

    # -- helpers --------------------------------------------------------------
    def pick_resume(self) -> None:
        path = filedialog.askopenfilename(
            title="Select your résumé PDF", filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
        if path:
            self.resume_path = path
            self.resume_label.config(text=f"✓ {os.path.basename(path)}", foreground="#177245")

    def open_sheet(self) -> None:
        path = config.workbook_path()
        if not path.exists():
            messagebox.showinfo("Relay", "No spreadsheet yet — run “Find jobs” first.")
            return
        try:
            os.startfile(str(path))  # Windows
        except AttributeError:
            import subprocess
            subprocess.run(["open" if os.uname().sysname == "Darwin" else "xdg-open", str(path)])

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_discover.config(state=state)
        self.btn_people.config(state=state)
        self.btn_save.config(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        if msg:
            self.status.set(msg)

    def _run_bg(self, work, on_done) -> None:
        """Run `work()` off the UI thread; hand (on_done, result, error) back via the
        queue so `_poll_results` can invoke on_done on the main thread.

        The worker must never call Tk directly (not thread-safe) — hence the queue.
        Callers guard re-entry via `_busy` *before* flipping it on (see the handlers).
        """

        def target():
            try:
                result, err = work(), None
            except Exception as exc:  # surfaced to the user, not swallowed
                result, err = None, exc
            self._results.put((on_done, result, err))

        threading.Thread(target=target, daemon=True).start()

    def _poll_results(self) -> None:
        """Main-thread pump: drain finished background work and run its callbacks."""
        try:
            while True:
                on_done, result, err = self._results.get_nowait()
                on_done(result, err)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_results)

    # -- save profile + preferences -------------------------------------------
    def run_save(self) -> None:
        """Persist the résumé + 'Looking for' text to profile.json without discovering."""
        if self._busy:
            return
        notes = self.notes.get()
        self._set_busy(True, "Saving your résumé + preferences…")

        def work():
            return flow.build_profile(self.resume_path, notes)

        def done(profile, err):
            self._set_busy(False)
            if err:
                self.status.set("Save failed.")
                messagebox.showerror("Relay", f"Save failed:\n{err}")
                return
            self.status.set(f"Saved — {profile.name}. Preferences stored; ready to find jobs.")

        self._run_bg(work, done)

    # -- step 1: discover jobs ------------------------------------------------
    def run_discover(self) -> None:
        if self._busy:
            return
        notes = self.notes.get()
        self._set_busy(True, f"Discovering jobs (mode: {config.jobs_mode()})… this can take a bit.")

        def work():
            profile = flow.build_profile(self.resume_path, notes)
            return flow.discover_jobs(profile)

        def done(jobs, err):
            self._set_busy(False)
            if err:
                self.status.set("Job discovery failed.")
                messagebox.showerror("Relay", f"Job discovery failed:\n{err}")
                return
            self.status.set(
                f"Found {len(jobs)} jobs → Jobs tab. Check ‘pursue’, then run step ②.")
            self.open_sheet()

        self._run_bg(work, done)

    # -- step 2: find people for checked jobs ---------------------------------
    def run_find_checked(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Finding people for the jobs you checked…")

        def work():
            from .resume import load_profile
            from .models import Profile
            return flow.find_people_for_checked_jobs(load_profile() or Profile(name="(unknown)"))

        def done(result, err):
            self._set_busy(False)
            if err:
                self.status.set("Finding people failed.")
                messagebox.showerror("Relay", f"Finding people failed:\n{err}")
                return
            contacts, companies = result
            if not contacts:
                self.status.set("No jobs checked — tick ‘pursue’ in the Jobs tab first.")
                messagebox.showinfo("Relay", "Check the ‘pursue’ box on some jobs first.")
                return
            self.status.set(
                f"Found {len(contacts)} contacts at {', '.join(sorted(set(companies)))} "
                "→ Contacts tab. Check ‘want_to_message’.")
            self.open_sheet()

        self._run_bg(work, done)


def launch() -> None:
    root = tk.Tk()
    RelayApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
